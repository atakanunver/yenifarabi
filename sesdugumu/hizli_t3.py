"""Chatterbox Multilingual T3 icin CUDA-graph'li hizli decode.

Kullanim:
    from hizli_t3 import hizlandir
    hizlandir(model)            # model: ChatterboxMultilingualTTS (ya da dogrudan T3)
    model.generate(...)         # artik hizli yol

Paket dosyalarina dokunmaz; t3.inference degistirilir (orijinali t3._inference_orijinal).
- Statik KV cache + tek adimlik decode (ornekleme dahil) CUDA graph icinde.
- Alignment analyzer (EOS bastirma / zorlama, tekrar korumasi) AYNEN korunur; katman 9/12/13 attention
  satiri graph ciktisi olarak host'a gelir, analyzer numpy'da calisir.
- Orijinal analyzer'in her cagrida hook biriktirme sorunu yok.
"""
import logging
import types

import numpy as np
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

SPY = [(12, 15), (13, 11), (9, 2)]  # (layer, head) -> LLAMA_ALIGNED_HEADS
NEG = -32768.0


class _Align:
    """AlignmentStreamAnalyzer.step'in numpy portu; logits yerine mod doner (0 normal, 1 EOS-bastir, 2 EOS-zorla)."""

    def __init__(self, S, maxrows):
        self.S = S
        self.A = np.zeros((maxrows, S), np.float32)
        self.n = 0
        self.curr = 0
        self.text_position = 0
        self.started = False
        self.started_at = None
        self.complete = False
        self.completed_at = None
        self.gen = []
        self.forced = None

    def step(self, chunk, next_token):
        S = self.S
        c = chunk.copy()
        c[:, self.curr + 1:] = 0
        r = c.shape[0]
        self.A[self.n:self.n + r] = c
        self.n += r
        A = self.A[:self.n]
        T = self.n
        cur = int(c[-1].argmax())
        disc = not (-4 < cur - self.text_position < 7)
        if not disc:
            self.text_position = cur
        false_start = (not self.started) and (A[-2:, -2:].max() > 0.1 or A[:, :4].max() < 0.5)
        self.started = not false_start
        if self.started and self.started_at is None:
            self.started_at = T
        self.complete = self.complete or self.text_position >= S - 3
        if self.complete and self.completed_at is None:
            self.completed_at = T
        long_tail = self.complete and (A[self.completed_at:, -3:].sum(0).max() >= 5)
        rep = False
        if self.complete and S > 5:
            sub = A[self.completed_at:, :-5]
            rep = sub.shape[0] > 0 and sub.max(1).sum() > 5
        if next_token is not None:
            self.gen.append(int(next_token))
            self.gen = self.gen[-8:]
        tok_rep = len(self.gen) >= 3 and len(set(self.gen[-2:])) == 1
        mode = 0
        if cur < S - 3 and S > 5:
            mode = 1
        if long_tail or rep or tok_rep:
            mode = 2
            self.forced = dict(long_tail=bool(long_tail), rep=bool(rep), tok_rep=bool(tok_rep), at=T)
        self.curr += 1
        return mode


class FastT3:
    def __init__(self, t3, dtype=torch.float32, lmax=1536, bucket=256, onisinma=True):
        self.t3 = t3
        self.dtype = dtype
        self.dev = t3.device
        self.lmax = lmax
        self.buckets = list(range(bucket, lmax + 1, bucket))
        tf = t3.tfmr
        cfg = t3.cfg
        self.nl = cfg.num_hidden_layers
        self.H = cfg.num_attention_heads
        self.D = cfg.head_dim
        self.C = cfg.hidden_size
        self.eps = cfg.rms_norm_eps
        self.scale = self.D ** -0.5
        dt = dtype
        with torch.inference_mode():
            self.Wqkv, self.Wo, self.Wgu, self.Wd, self.n1, self.n2 = [], [], [], [], [], []
            for L in tf.layers:
                a, m = L.self_attn, L.mlp
                self.Wqkv.append(torch.cat([a.q_proj.weight, a.k_proj.weight, a.v_proj.weight]).to(dt).contiguous())
                self.Wo.append(a.o_proj.weight.to(dt).contiguous())
                self.Wgu.append(torch.cat([m.gate_proj.weight, m.up_proj.weight]).to(dt).contiguous())
                self.Wd.append(m.down_proj.weight.to(dt).contiguous())
                self.n1.append(L.input_layernorm.weight.to(dt).contiguous())
                self.n2.append(L.post_attention_layernorm.weight.to(dt).contiguous())
            self.nf = tf.norm.weight.to(dt).contiguous()
            self.head_w = t3.speech_head.weight.to(dt).contiguous()
            assert t3.speech_head.bias is None
            self.emb_w = t3.speech_emb.weight.to(dt).contiguous()
            self.pos_w = t3.speech_pos_emb.emb.weight.to(dt).contiguous()
            self.V = self.head_w.shape[0]
            pid = torch.arange(lmax, device=self.dev)[None]
            cos, sin = tf.rotary_emb(torch.zeros(1, lmax, self.C, device=self.dev, dtype=torch.float32), pid)
            self.cos = cos[0].to(dt).contiguous()  # (lmax, D)
            self.sin = sin[0].to(dt).contiguous()
            self.K = torch.zeros(self.nl, 2, self.H, lmax, self.D, device=self.dev, dtype=dt)
            self.Vc = torch.zeros_like(self.K)
            self.ar = torch.arange(lmax, device=self.dev)
            # statik durum
            self.raw = torch.zeros(1, self.V, device=self.dev, dtype=torch.float32)
            self.mode = torch.zeros(1, dtype=torch.long, device=self.dev)
            self.seen = torch.zeros(1, self.V, dtype=torch.bool, device=self.dev)
            self.pos = torch.zeros(1, dtype=torch.long, device=self.dev)
            self.spos = torch.ones(1, dtype=torch.long, device=self.dev)
            self.out = torch.zeros(1 + lmax, device=self.dev, dtype=torch.float32)
            self.out_host = torch.zeros(1 + lmax, dtype=torch.float32).pin_memory()
            self.mode_pin = torch.zeros(1, dtype=torch.long).pin_memory()
            self.eos = t3.hp.stop_speech_token
            self.bos = t3.hp.start_speech_token
            self.eos_onehot = torch.zeros(1, self.V, dtype=torch.bool, device=self.dev)
            self.eos_onehot[0, self.eos] = True
            self.force_vec = torch.full((1, self.V), NEG, device=self.dev)
            self.force_vec[0, self.eos] = -NEG
            self.negv = torch.full((1, self.V), NEG, device=self.dev)
            self.spy = {}
            for slot, (lay, head) in enumerate(SPY):
                self.spy.setdefault(lay, []).append((slot, head))
        self.pool = torch.cuda.graph_pool_handle()
        self.graphs = {}
        self.stats = {}
        if onisinma:
            self.yakala_hepsi()

    # ---------------- ortak parcalar ----------------
    @staticmethod
    def _rot_half(x):
        h = x.shape[-1] // 2
        return torch.cat((-x[..., h:], x[..., :h]), dim=-1)

    def _rms(self, x, w):
        return F.rms_norm(x, (self.C,), w, self.eps)

    # ---------------- prefill (eager) ----------------
    @torch.inference_mode()
    def prefill(self, embeds, sl):
        """embeds (2,T,C). Doner: raw logits (1,V) CFG'siz ham (2,V), ve ilk analyzer parcasi (2,S)."""
        B, T, C = embeds.shape
        H, D = self.H, self.D
        x = embeds.to(self.dtype)
        cos, sin = self.cos[:T][None, None], self.sin[:T][None, None]
        i, j = sl
        rows = []
        for l in range(self.nl):
            h = self._rms(x, self.n1[l])
            qkv = F.linear(h, self.Wqkv[l])
            q, k, v = qkv.split(C, dim=-1)
            q = q.view(B, T, H, D).transpose(1, 2)
            k = k.view(B, T, H, D).transpose(1, 2)
            v = v.view(B, T, H, D).transpose(1, 2)
            q = q * cos + self._rot_half(q) * sin
            k = k * cos + self._rot_half(k) * sin
            self.K[l, :, :, :T] = k
            self.Vc[l, :, :, :T] = v
            a = F.scaled_dot_product_attention(q, k, v, is_causal=True)
            for slot, head in self.spy.get(l, []):
                s = (q[0, head, -2:] @ k[0, head].T).float() * self.scale  # (2,T)
                m = torch.arange(T, device=s.device)[None] > (torch.arange(T - 2, T, device=s.device)[:, None])
                s = s.masked_fill(m, float("-inf"))
                rows.append(torch.softmax(s, -1)[:, i:j])
            a = a.transpose(1, 2).reshape(B, T, C)
            x = x + F.linear(a, self.Wo[l])
            h = self._rms(x, self.n2[l])
            g, u = F.linear(h, self.Wgu[l]).chunk(2, dim=-1)
            x = x + F.linear(F.silu(g) * u, self.Wd[l])
        x = self._rms(x[:, -1], self.nf)
        lg = F.linear(x, self.head_w).float()  # (2,V)
        A0 = torch.stack(rows).mean(0)  # (2,S)
        return lg, A0

    # ---------------- decode adimi (graph icinde) ----------------
    def _sample(self, p):
        l = self.raw
        m = self.mode
        l = torch.where(m == 2, self.force_vec, l)
        l = torch.where((m == 1) & self.eos_onehot, self.negv, l)
        pen = p["rep"]
        l = torch.where(self.seen, torch.where(l < 0, l * pen, l / pen), l)
        if p["temp"] != 1.0:
            l = l / p["temp"]
        if p["min_p"] > 0:
            pr = torch.softmax(l, -1)
            l = l.masked_fill(pr < p["min_p"] * pr.max(-1, keepdim=True).values, float("-inf"))
        if p["top_p"] < 1.0:
            sl, si = torch.sort(l, dim=-1, descending=False)
            cum = torch.softmax(sl, -1).cumsum(-1)
            rm = cum <= (1 - p["top_p"])
            rm[..., -1:] = False
            l = l.masked_fill(rm.scatter(1, si, rm), float("-inf"))
        probs = torch.softmax(l, -1)
        return torch.multinomial(probs, 1)  # (1,1)

    def _step(self, Lb, p):
        C, H, D = self.C, self.H, self.D
        tok = self._sample(p)
        self.seen.index_fill_(1, tok.view(-1), True)
        self.out[:1].copy_(tok.view(1).float())
        e = (self.emb_w[tok.view(-1)] + self.pos_w[self.spos]).view(1, 1, C)
        x = torch.cat([e, e])  # (2,1,C)
        pos = self.pos
        cos = self.cos[pos].view(1, 1, 1, D)
        sin = self.sin[pos].view(1, 1, 1, D)
        bias = torch.where(self.ar[:Lb] <= pos, 0.0, float("-inf")).view(1, 1, 1, Lb)
        spy_rows = []
        for l in range(self.nl):
            h = self._rms(x, self.n1[l])
            q, k, v = F.linear(h, self.Wqkv[l]).split(C, dim=-1)
            q = q.view(2, 1, H, D).transpose(1, 2)
            k = k.view(2, 1, H, D).transpose(1, 2)
            v = v.view(2, 1, H, D).transpose(1, 2)
            q = q * cos + self._rot_half(q) * sin
            k = k * cos + self._rot_half(k) * sin
            self.K[l].index_copy_(2, pos, k)
            self.Vc[l].index_copy_(2, pos, v)
            kc = self.K[l][:, :, :Lb]
            vc = self.Vc[l][:, :, :Lb]
            s = torch.matmul(q, kc.transpose(-1, -2)).float() * self.scale + bias  # (2,H,1,Lb)
            w = torch.softmax(s, -1)
            for slot, head in self.spy.get(l, []):
                spy_rows.append(w[0, head, 0])
            a = torch.matmul(w.to(self.dtype), vc)  # (2,H,1,D)
            a = a.transpose(1, 2).reshape(2, 1, C)
            x = x + F.linear(a, self.Wo[l])
            h = self._rms(x, self.n2[l])
            g, u = F.linear(h, self.Wgu[l]).chunk(2, dim=-1)
            x = x + F.linear(F.silu(g) * u, self.Wd[l])
        x = self._rms(x[:, 0], self.nf)
        lg = F.linear(x, self.head_w).float()
        cond, unc = lg[0:1], lg[1:2]
        self.raw.copy_(cond + p["cfg"] * (cond - unc))
        self.out[1:1 + Lb].copy_(torch.stack(spy_rows).mean(0))
        self.pos.add_(1)
        self.spos.add_(1)

    @torch.inference_mode()
    def _capture(self, Lb, p):
        key = (Lb,) + tuple(sorted(p.items()))
        if key in self.graphs:
            return self.graphs[key]
        snap = [t.clone() for t in (self.raw, self.mode, self.seen, self.pos, self.spos)]
        s = torch.cuda.Stream()
        s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s), torch.inference_mode():
            for _ in range(2):
                self._step(Lb, p)
        torch.cuda.current_stream().wait_stream(s)
        torch.cuda.synchronize()
        g = torch.cuda.CUDAGraph()
        with torch.inference_mode(), torch.cuda.graph(g, pool=self.pool):
            self._step(Lb, p)
        torch.cuda.synchronize()
        for t, o in zip((self.raw, self.mode, self.seen, self.pos, self.spos), snap):
            t.copy_(o)
        self.graphs[key] = g
        return g

    @staticmethod
    def _params(temperature, top_p, min_p, rep, cfg):
        return dict(temp=float(temperature), top_p=float(top_p), min_p=float(min_p), rep=float(rep), cfg=float(cfg))

    def yakala_hepsi(self, temperature=0.8, top_p=1.0, min_p=0.05, rep=2.0, cfg=0.5):
        p = self._params(temperature, top_p, min_p, rep, cfg)
        for Lb in self.buckets:
            self._capture(Lb, p)

    # ---------------- uretim ----------------
    @torch.inference_mode()
    def run(self, embeds, sl, max_new, p):
        T = embeds.shape[1]
        i, j = sl
        S = j - i
        max_new = min(max_new, self.lmax - T - 1)
        lg, A0 = self.prefill(embeds, sl)
        cond, unc = lg[0:1], lg[1:2]
        self.raw.copy_(cond + p["cfg"] * (cond - unc))
        self.pos.fill_(T)
        self.spos.fill_(1)
        self.seen.zero_()
        self.seen[0, self.bos] = True
        az = _Align(S, max_new + 4)
        chunk = A0.cpu().numpy()
        last = self.bos
        toks = []
        cur_graph = None
        cur_Lb = 0
        for n in range(max_new):
            mode = az.step(chunk, last)
            self.mode_pin[0] = mode
            self.mode.copy_(self.mode_pin, non_blocking=True)
            need = T + n + 1
            if need > cur_Lb:
                cur_Lb = next(b for b in self.buckets if b >= need)
                cur_graph = self._capture(cur_Lb, p)
            cur_graph.replay()
            self.out_host.copy_(self.out, non_blocking=True)
            torch.cuda.current_stream().synchronize()
            o = self.out_host.numpy()
            tok = int(o[0])
            toks.append(tok)
            if tok == self.eos:
                break
            chunk = o[1 + i:1 + j].reshape(1, S)
            last = tok
        self.stats = dict(forced=az.forced, steps=len(toks), T=T)
        return torch.tensor([toks], dtype=torch.long, device=self.dev)


def hizlandir(model, dtype=torch.float32, lmax=1536, onisinma=True):
    """model: ChatterboxMultilingualTTS veya T3. Doner: FastT3 (model.t3.hizli ile de erisilir)."""
    t3 = model.t3 if hasattr(model, "t3") else model
    if getattr(t3, "hizli", None) is not None:
        return t3.hizli
    assert t3.hp.is_multilingual, "yalnizca cok dilli model"
    fast = FastT3(t3, dtype=dtype, lmax=lmax, onisinma=onisinma)
    orig = t3.inference
    t3._inference_orijinal = orig
    t3.hizli = fast

    @torch.inference_mode()
    def inference(self, *, t3_cond, text_tokens, initial_speech_tokens=None, prepend_prompt_speech_tokens=None,
                  num_return_sequences=1, max_new_tokens=None, stop_on_eos=True, do_sample=True, temperature=0.8,
                  top_p=0.95, min_p=0.05, length_penalty=1.0, repetition_penalty=1.2, cfg_weight=0.5):
        tt = torch.atleast_2d(text_tokens)
        if (prepend_prompt_speech_tokens is not None or num_return_sequences != 1 or not stop_on_eos
                or not do_sample or tt.size(0) != 2 or not (cfg_weight > 0)):
            return orig(t3_cond=t3_cond, text_tokens=text_tokens, initial_speech_tokens=initial_speech_tokens,
                        prepend_prompt_speech_tokens=prepend_prompt_speech_tokens,
                        num_return_sequences=num_return_sequences, max_new_tokens=max_new_tokens,
                        stop_on_eos=stop_on_eos, do_sample=do_sample, temperature=temperature, top_p=top_p,
                        min_p=min_p, length_penalty=length_penalty, repetition_penalty=repetition_penalty,
                        cfg_weight=cfg_weight)
        from chatterbox.models.t3.t3 import _ensure_BOT_EOT
        _ensure_BOT_EOT(text_tokens, self.hp)
        text_tokens = tt.to(dtype=torch.long, device=self.device)
        if initial_speech_tokens is None:
            initial_speech_tokens = self.hp.start_speech_token * torch.ones_like(text_tokens[:, :1])
        embeds, len_cond = self.prepare_input_embeds(t3_cond=t3_cond, text_tokens=text_tokens,
                                                     speech_tokens=initial_speech_tokens, cfg_weight=cfg_weight)
        bos = torch.tensor([[self.hp.start_speech_token]], dtype=torch.long, device=embeds.device)
        be = self.speech_emb(bos) + self.speech_pos_emb.get_fixed_embedding(0)
        embeds = torch.cat([embeds, torch.cat([be, be])], dim=1)
        sl = (len_cond, len_cond + text_tokens.size(-1))
        p = FastT3._params(temperature, top_p, min_p, repetition_penalty, cfg_weight)
        return fast.run(embeds, sl, max_new_tokens or self.hp.max_speech_tokens, p)

    t3.inference = types.MethodType(inference, t3)
    return fast
