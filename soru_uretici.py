"""soru_uretici.py - Sınıf Arenası Hibrit Soru Motoru.

1. Hazır Müfredat Havuzu: Anında (0 sn) yüklenen yüksek kaliteli MEB soruları.
2. Farabi RAG + Ollama (qwen3.8:27b) Canlı Üretim: Tek tıkla MEB ders kitabından
   sayfa referanslı taze Jeopardy soruları üretir.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any
import httpx

import turkce

log = logging.getLogger("soru_uretici")

API_KEYS_YOLU = Path("/home/ata/farabi/server/config/api_keys.json")
FARABI_API_URL = "http://127.0.0.1:8000"
OLLAMA_URL = "http://127.0.0.1:11434"

KAPSAM_ESLEME: dict[str, str] = {   'biyoloji': 'biyoloji',
    'kimya': 'kimya',
    'fizik': 'fizik',
    'matematik': 'matematik',
    'temel matematik': 'matematik',
    'matematik uygulamaları': 'matematik',
    'tarih': 'tarih',
    'inkılap tarihi ve atatürkçülük': 'tarih',
    't.c. inkılap tarihi ve atatürkçülük': 'tarih',
    'çağdaş türk ve dünya tarihi': 'tarih',
    'türk dili ve edebiyatı': 'edebiyat',
    'edebiyat': 'edebiyat',
    'osmanlı türkçesi': 'edebiyat',
    'coğrafya': 'cografya',
    'cografya': 'cografya',
    'felsefe': 'felsefe',
    'psikoloji': 'felsefe',
    'mantık': 'felsefe',
    'din kültürü ve ahlak bilgisi': 'din',
    'din': 'din',
    'peygamberimizin hayatı': 'din',
    'temel dini bilgiler': 'din',
    'ingilizce': 'ingilizce',
    'almanca': 'almanca',
    'yabancı dil': 'ingilizce',
    'bilişim teknolojileri ve yazılım': 'bilisim',
    'bilişim teknolojileri': 'bilisim',
    'bilişim': 'bilisim',
    'bilgisayar bilimi': 'bilisim',
    'yazılım': 'bilisim',
    'sağlık bilgisi ve trafik kültürü': 'saglik',
    'sağlık bilgisi': 'saglik',
    'sağlık': 'saglik',
    'trafik': 'saglik',
    'beden eğitimi': 'saglik',
    'beden eğitimi ve spor': 'saglik',
    'spor etkinlikleri': 'saglik',
    'ortak türk tarihi': 'tarih',
    'görsel sanatlar': 'gorsel_sanatlar',
    'görsel sanatlar ve müzik': 'gorsel_sanatlar',
    'gorsel_sanatlar': 'gorsel_sanatlar',
    'müzik': 'gorsel_sanatlar',
    'sanat': 'gorsel_sanatlar',
    'rehberlik': 'genel',
    'sınav hazırlık çalışması': 'genel',
    'hedef fizik': 'fizik',
    'hedef kimya': 'kimya',
    'hedef biyoloji': 'biyoloji',
    'hedef matematik': 'matematik',
    'hedef coğrafya': 'cografya',
    'hedef cografya': 'cografya',
    'hedef tarih': 'tarih',
    'genel kültür': 'genel'}


VARSAYILAN_SORULAR: dict[str, list[dict[str, Any]]] = {   'biyoloji': [   {   'id': 'bio_1',
                        'name': 'Hücre Zarı & Geçişler',
                        'color': 'from-emerald-600 to-teal-600',
                        'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Hücre zarının yapısını açıklayan güncel zar modelinin adı nedir?',
                                             'a': 'Akıcı Mozaik Zar Modeli',
                                             'kaynak': 'MEB Biyoloji 9, s. 124',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'Hücre zarından madde geçişinde ATP harcanarak az yoğundan çok '
                                                  'yoğuna yapılan geçişe ne denir?',
                                             'a': 'Aktif Taşıma',
                                             'kaynak': 'MEB Biyoloji 9, s. 133',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Suyun yarı geçirgen bir zardan çok yoğun ortama doğru difüzyonuna '
                                                  'ne ad verilir?',
                                             'a': 'Osmoz',
                                             'kaynak': 'MEB Biyoloji 9, s. 136',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Büyük katı maddelerin hücre zarının yalancı ayaklar oluşturarak '
                                                  'hücre içine almasına ne denir?',
                                             'a': 'Fagositoz',
                                             'kaynak': 'MEB Biyoloji 9, s. 140',
                                             'answered': False}]},
                    {   'id': 'bio_2',
                        'name': 'Organeller & Görevleri',
                        'color': 'from-teal-600 to-cyan-600',
                        'badgeColor': 'text-teal-400 bg-teal-500/20 border-teal-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Hücrede oksijenli solunumla ATP (enerji) üreten çift zarlı organel '
                                                  'hangisidir?',
                                             'a': 'Mitokondri',
                                             'kaynak': 'MEB Biyoloji 9, s. 145',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'Zarsız olan ve protein sentezinden sorumlu olan tüm hücrelerde '
                                                  'bulunan organel nedir?',
                                             'a': 'Ribozom',
                                             'kaynak': 'MEB Biyoloji 9, s. 142',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Hücre içi sindirimi gerçekleştiren ve hidrolitik enzimler içeren '
                                                  'organel hangisidir?',
                                             'a': 'Lizozom',
                                             'kaynak': 'MEB Biyoloji 9, s. 148',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Salgı maddelerinin paketlenmesi, modifikasyonu ve depolanmasında '
                                                  'görevli yassılaşmış kesecikler hangisidir?',
                                             'a': 'Golgi Aygıtı',
                                             'kaynak': 'MEB Biyoloji 9, s. 146',
                                             'answered': False}]},
                    {   'id': 'bio_3',
                        'name': 'Canlıların Temel Bileşenleri',
                        'color': 'from-green-600 to-emerald-600',
                        'badgeColor': 'text-green-400 bg-green-500/20 border-green-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Vücudumuzun birincil ve en hızlı enerji kaynağı olan organik '
                                                  'molekül grubu nedir?',
                                             'a': 'Karbonhidratlar',
                                             'kaynak': 'MEB Biyoloji 9, s. 55',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'Proteinlerin yapı taşları olan 20 farklı monomer çeşidine ne ad '
                                                  'verilir?',
                                             'a': 'Amino Asitler',
                                             'kaynak': 'MEB Biyoloji 9, s. 68',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Biyokimyasal tepkimelerin aktivasyon enerjisini düşüren biyolojik '
                                                  'katalizörler nelerdir?',
                                             'a': 'Enzimler',
                                             'kaynak': 'MEB Biyoloji 9, s. 82',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Hücre zarı yapısına katılan ve bir gliserol ile iki yağ asidi ve '
                                                  'bir fosfat grubundan oluşan lipit çeşidi nedir?',
                                             'a': 'Fosfolipit',
                                             'kaynak': 'MEB Biyoloji 9, s. 64',
                                             'answered': False}]},
                    {   'id': 'bio_4',
                        'name': 'Nükleik Asitler & Yaşam',
                        'color': 'from-lime-600 to-green-600',
                        'badgeColor': 'text-lime-400 bg-lime-500/20 border-lime-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Genetik bilgiyi taşıyan ve çift sarmallı yapıya sahip nükleik asit '
                                                  'hangisidir?',
                                             'a': 'DNA (Deoksiribonükleik Asit)',
                                             'kaynak': 'MEB Biyoloji 9, s. 95',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': "DNA'da Guanin bazının karşısına her zaman hangi azotlu organik baz "
                                                  'gelir?',
                                             'a': 'Sitozin (C/S)',
                                             'kaynak': 'MEB Biyoloji 9, s. 97',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Hücrede hazır kullanılabilir enerji para birimi olan molekülün '
                                                  'kısaltması nedir?',
                                             'a': 'ATP (Adenozin Trifosfat)',
                                             'kaynak': 'MEB Biyoloji 9, s. 104',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': "Yalnızca RNA yapısında bulunan ve DNA'daki Timin yerine geçen "
                                                  'pirimidin bazı hangisidir?',
                                             'a': 'Urasil',
                                             'kaynak': 'MEB Biyoloji 9, s. 100',
                                             'answered': False}]}],
    'matematik': [   {   'id': 'mat_1',
                         'name': 'Sayı Kümeleri & Bölünebilme',
                         'color': 'from-blue-600 to-indigo-600',
                         'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                         'questions': [   {   'points': 100,
                                              'q': 'En küçük asal sayı kaçtır ve bu asal sayının çift olma özelliği '
                                                   'nedir?',
                                              'a': '2 (Tek çift asal sayıdır)',
                                              'kaynak': 'MEB Matematik 9, s. 42',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': 'Bir sayının 3 ile tam bölünebilmesi için hangi kuralın sağlanması '
                                                   'gerekir?',
                                              'a': "Rakamları toplamının 3'ün katı olması",
                                              'kaynak': 'MEB Matematik 9, s. 55',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': 'İki basamaklı en büyük asal sayı kaçtır?',
                                              'a': '97',
                                              'kaynak': 'MEB Matematik 9, s. 46',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': "Aralarında asal iki sayının EBOB'u kaçtır?",
                                              'a': "1'dir",
                                              'kaynak': 'MEB Matematik 9, s. 68',
                                              'answered': False}]},
                     {   'id': 'mat_2',
                         'name': 'Denklemler & Eşitsizlikler',
                         'color': 'from-indigo-600 to-purple-600',
                         'badgeColor': 'text-indigo-400 bg-indigo-500/20 border-indigo-500/40',
                         'questions': [   {   'points': 100,
                                              'q': '3x - 7 = 14 denkleminde x kaçtır?',
                                              'a': 'x = 7 (3x = 21)',
                                              'kaynak': 'MEB Matematik 9, s. 110',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': 'Bir sayının 4 katının 5 eksiği 27 ise bu sayı kaçtır?',
                                              'a': '8 (4x - 5 = 27 -> 4x = 32)',
                                              'kaynak': 'MEB Matematik 9, s. 114',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': '|x - 3| = 5 denkleminin çözüm kümesi hangi sayılardan oluşur?',
                                              'a': '{-2, 8}',
                                              'kaynak': 'MEB Matematik 9, s. 132',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': '2x - 3 < 7 eşitsizliğini sağlayan en büyük x tam sayısı kaçtır?',
                                              'a': '4 (2x < 10 -> x < 5)',
                                              'kaynak': 'MEB Matematik 9, s. 125',
                                              'answered': False}]},
                     {   'id': 'mat_3',
                         'name': 'Üslü & Köklü İfadeler',
                         'color': 'from-purple-600 to-pink-600',
                         'badgeColor': 'text-purple-400 bg-purple-500/20 border-purple-500/40',
                         'questions': [   {   'points': 100,
                                              'q': '2 üzeri 5 (2⁵) ifadesinin değeri kaçtır?',
                                              'a': '32',
                                              'kaynak': 'MEB Matematik 9, s. 145',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': 'Karekök 144 (√144) sayısı kaça eşittir?',
                                              'a': '12',
                                              'kaynak': 'MEB Matematik 9, s. 160',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': '3⁻² ifadesinin rasyonel sayı olarak değeri nedir?',
                                              'a': '1/9',
                                              'kaynak': 'MEB Matematik 9, s. 148',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': '√50 ifadesinin a√b şeklinde en sade yazılışı nedir?',
                                              'a': '5√2',
                                              'kaynak': 'MEB Matematik 9, s. 165',
                                              'answered': False}]},
                     {   'id': 'mat_4',
                         'name': 'Kümeler & Mantık',
                         'color': 'from-cyan-600 to-blue-600',
                         'badgeColor': 'text-cyan-400 bg-cyan-500/20 border-cyan-500/40',
                         'questions': [   {   'points': 100,
                                              'q': 'Eleman sayısı 4 olan bir kümenin alt küme sayısı kaçtır?',
                                              'a': '16 (2⁴ = 16)',
                                              'kaynak': 'MEB Matematik 9, s. 22',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': 'Hiçbir elemanı olmayan kümeye ne ad verilir ve sembolü nedir?',
                                              'a': 'Boş Küme (Ø veya {})',
                                              'kaynak': 'MEB Matematik 9, s. 18',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': "p ∧ p' (p VE p'nin değili) önermesinin doğruluk değeri nedir?",
                                              'a': '0 (Yanlış)',
                                              'kaynak': 'MEB Mantık 9, s. 12',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': 's(A)=8, s(B)=6 ve s(A ∩ B)=3 ise s(A ∪ B) kaçtır?',
                                              'a': '11 (8 + 6 - 3)',
                                              'kaynak': 'MEB Matematik 9, s. 30',
                                              'answered': False}]}],
    'kimya': [   {   'id': 'kim_1',
                     'name': 'Atom & Periyodik Sistem',
                     'color': 'from-amber-600 to-orange-600',
                     'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Atom çekirdeğinde bulunan pozitif yüklü temel tanecik hangisidir?',
                                          'a': 'Proton',
                                          'kaynak': 'MEB Kimya 9, s. 65',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Periyodik tablonun 8A grubunda bulunan kararlı element grubuna ne ad '
                                               'verilir?',
                                          'a': 'Soygazlar (Asal Gazlar)',
                                          'kaynak': 'MEB Kimya 9, s. 85',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Proton sayıları aynı, nötron sayıları farklı olan atomlara ne denir?',
                                          'a': 'İzotop Atomlar',
                                          'kaynak': 'MEB Kimya 9, s. 72',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Periyodik sistemde aynı periyotta soldan sağa doğru gidildikçe atom '
                                               'yarıçapı nasıl değişir?',
                                          'a': 'Azalır (Küçülür)',
                                          'kaynak': 'MEB Kimya 9, s. 92',
                                          'answered': False}]},
                 {   'id': 'kim_2',
                     'name': 'Kimyasal Türler Arası Etkileşimler',
                     'color': 'from-orange-600 to-rose-600',
                     'badgeColor': 'text-orange-400 bg-orange-500/20 border-orange-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Metaller ile ametaller arasında elektron alışverişiyle oluşan bağ türü '
                                               'nedir?',
                                          'a': 'İyonik Bağ',
                                          'kaynak': 'MEB Kimya 9, s. 115',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Ametaller arasında elektronların ortaklaşa kullanılmasıyla oluşan '
                                               'güçlü bağ nedir?',
                                          'a': 'Kovalent Bağ',
                                          'kaynak': 'MEB Kimya 9, s. 122',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Su molekülleri arasında oluşan ve yüksek kaynama noktasına yol açan '
                                               'zayıf etkileşim hangisidir?',
                                          'a': 'Hidrojen Bağı',
                                          'kaynak': 'MEB Kimya 9, s. 138',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Soygazlar ve apolar moleküller arasında anlık indüklenmiş dipollerle '
                                               'oluşan zayıf bağ nedir?',
                                          'a': 'London Kuvvetleri',
                                          'kaynak': 'MEB Kimya 9, s. 142',
                                          'answered': False}]},
                 {   'id': 'kim_3',
                     'name': 'Maddenin Halleri',
                     'color': 'from-red-600 to-amber-600',
                     'badgeColor': 'text-red-400 bg-red-500/20 border-red-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Bir maddenin katı halden doğrudan gaz haline geçmesine ne ad verilir?',
                                          'a': 'Süblimleşme',
                                          'kaynak': 'MEB Kimya 9, s. 160',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Sıvıların akmaya karşı gösterdiği iç dirence ne denir?',
                                          'a': 'Viskozite',
                                          'kaynak': 'MEB Kimya 9, s. 168',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'İyonize olmuş gaz, serbest elektronlar ve iyonlardan oluşan maddenin '
                                               '4. hali nedir?',
                                          'a': 'Plazma Hali',
                                          'kaynak': 'MEB Kimya 9, s. 182',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Açık hava basıncının 1 atm olduğu ortamda saf suyun kaynama sıcaklığı '
                                               "kaç °C'dir?",
                                          'a': '100 °C',
                                          'kaynak': 'MEB Kimya 9, s. 172',
                                          'answered': False}]},
                 {   'id': 'kim_4',
                     'name': 'Asitler, Bazlar & Tuzlar',
                     'color': 'from-yellow-600 to-amber-600',
                     'badgeColor': 'text-yellow-400 bg-yellow-500/20 border-yellow-500/40',
                     'questions': [   {   'points': 100,
                                          'q': "Sulu çözeltilerinde pH değeri 7'den küçük olan maddeler hangi sınıfa "
                                               'girer?',
                                          'a': 'Asitler',
                                          'kaynak': 'MEB Kimya 10, s. 120',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Asitler mavi turnusol kağıdının rengini hangi renge dönüştürür?',
                                          'a': 'Kırmızı',
                                          'kaynak': 'MEB Kimya 10, s. 124',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Bir asit ile bir bazın tepkimeye girerek tuz ve su oluşturması olayına '
                                               'ne denir?',
                                          'a': 'Nötrleşme (Nötralleşme) Tepkimesi',
                                          'kaynak': 'MEB Kimya 10, s. 135',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Tuz ruhu olarak bilinen güçlü asidin kimyasal formülü nedir?',
                                          'a': 'HCl (Hidroklorik Asit)',
                                          'kaynak': 'MEB Kimya 10, s. 150',
                                          'answered': False}]}],
    'tarih': [   {   'id': 'tar_1',
                     'name': 'İlk Çağ & Türk Tarihi',
                     'color': 'from-amber-700 to-yellow-600',
                     'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Tarihte bilinen ilk Türk devleti hangisidir?',
                                          'a': 'Asya Hun Devleti',
                                          'kaynak': 'MEB Tarih 9, s. 75',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "Türk ordusunda 'Onluk Sistem'i kurarak Türk Kara Kuvvetleri'nin "
                                               'temellerini atan Hun hükümdarı kimdir?',
                                          'a': 'Mete Han (M.Ö. 209)',
                                          'kaynak': 'MEB Tarih 9, s. 82',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Türk adıyla kurulan ilk devlet hangisidir ve ilk alfabemiz nedir?',
                                          'a': 'Köktürk Devleti (Orhun Alfabesi)',
                                          'kaynak': 'MEB Tarih 9, s. 94',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Uygurların benimsediği ve et yemeyi, savaşmayı yasaklayan inanç '
                                               'sistemi nedir?',
                                          'a': 'Maniheizm (Mani Dini)',
                                          'kaynak': 'MEB Tarih 9, s. 108',
                                          'answered': False}]},
                 {   'id': 'tar_2',
                     'name': 'İslamiyet & Türkler',
                     'color': 'from-yellow-700 to-amber-600',
                     'badgeColor': 'text-yellow-400 bg-yellow-500/20 border-yellow-500/40',
                     'questions': [   {   'points': 100,
                                          'q': "Türklerin kitleler halinde İslamiyet'i kabul etmesinde dönüm noktası "
                                               'olan 751 yılındaki savaş nedir?',
                                          'a': 'Talas Savaşı',
                                          'kaynak': 'MEB Tarih 9, s. 142',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "Orta Asya'da kurulan ilk Müslüman Türk devleti hangisidir?",
                                          'a': 'Karahanlılar',
                                          'kaynak': 'MEB Tarih 9, s. 155',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': "1071 yılında Anadolu'nun kapılarını Türklere açan zafer hangisidir ve "
                                               'komutanı kimdir?',
                                          'a': 'Malazgirt Zaferi (Sultan Alparslan)',
                                          'kaynak': 'MEB Tarih 9, s. 178',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': "Yusuf Has Hacib tarafından yazılan ve 'mutluluk veren bilgi' anlamına "
                                               'gelen ilk Türkçe İslami eser nedir?',
                                          'a': 'Kutadgu Bilig',
                                          'kaynak': 'MEB Tarih 9, s. 162',
                                          'answered': False}]},
                 {   'id': 'tar_3',
                     'name': "Osmanlı Devleti'nin Kuruluşu",
                     'color': 'from-red-800 to-amber-700',
                     'badgeColor': 'text-red-400 bg-red-500/20 border-red-500/40',
                     'questions': [   {   'points': 100,
                                          'q': "Osmanlı Devleti'nin kurucusu olan ilk padişah kimdir?",
                                          'a': 'Osman Gazi',
                                          'kaynak': 'MEB Tarih 10, s. 25',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "Osmanlı Devleti'nin Bizans İmparatorluğu ile yaptığı ilk savaşın adı "
                                               'nedir (1302)?',
                                          'a': 'Koyunhisar (Bafeus) Savaşı',
                                          'kaynak': 'MEB Tarih 10, s. 34',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': "Bursa'yı fethederek başkent yapan ve ilk düzenli orduyu kuran Osmanlı "
                                               'padişahı kimdir?',
                                          'a': 'Orhan Gazi',
                                          'kaynak': 'MEB Tarih 10, s. 42',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': "Osmanlı'nın Rumeli'ye geçişinde üs olarak kullanılan ve Gelibolu'da "
                                               'alınan ilk kale hangisidir?',
                                          'a': 'Çimpe Kalesi (1353)',
                                          'kaynak': 'MEB Tarih 10, s. 48',
                                          'answered': False}]},
                 {   'id': 'tar_4',
                     'name': 'Milli Mücadele & Cumhuriyet',
                     'color': 'from-rose-700 to-red-600',
                     'badgeColor': 'text-rose-400 bg-rose-500/20 border-rose-500/40',
                     'questions': [   {   'points': 100,
                                          'q': "Mustafa Kemal Atatürk'ün Samsun'a çıkarak Milli Mücadele'yi fiilen "
                                               'başlattığı tarih nedir?',
                                          'a': '19 Mayıs 1919',
                                          'kaynak': 'MEB İnkılap Tarihi 12, s. 45',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "'Milletin bağımsızlığını yine milletin azim ve kararı kurtaracaktır' "
                                               'kararı hangi genelgede alınmıştır?',
                                          'a': 'Amasya Genelgesi',
                                          'kaynak': 'MEB İnkılap Tarihi 12, s. 52',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': "Türkiye Büyük Millet Meclisi (TBMM) hangi tarihte Ankara'da "
                                               'açılmıştır?',
                                          'a': '23 Nisan 1920',
                                          'kaynak': 'MEB İnkılap Tarihi 12, s. 78',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': "Kurtuluş Savaşı'nın askeri safhasını zaferle sonlandıran 30 Ağustos "
                                               'zaferinin resmi adı nedir?',
                                          'a': 'Başkumandanlık Meydan Muharebesi (Büyük Taarruz)',
                                          'kaynak': 'MEB İnkılap Tarihi 12, s. 115',
                                          'answered': False}]}],
    'türk dili ve edebiyatı': [   {   'id': 'tde_1',
                                      'name': 'Edebi Türler & Hikaye',
                                      'color': 'from-purple-700 to-indigo-600',
                                      'badgeColor': 'text-purple-400 bg-purple-500/20 border-purple-500/40',
                                      'questions': [   {   'points': 100,
                                                           'q': 'Edebiyatımızda Batılı anlamda ilk hikaye örneği '
                                                                "sayılan Letaif-i Rivayat'ın yazarı kimdir?",
                                                           'a': 'Ahmet Mithat Efendi',
                                                           'kaynak': 'MEB Edebiyat 9, s. 35',
                                                           'answered': False},
                                                       {   'points': 200,
                                                           'q': 'Serim, düğüm ve çözüm bölümlerinden oluşan olay '
                                                                'hikayeciliğinin (klasik hikaye) dünya edebiyatındaki '
                                                                'öncüsü kimdir?',
                                                           'a': 'Guy de Maupassant',
                                                           'kaynak': 'MEB Edebiyat 9, s. 42',
                                                           'answered': False},
                                                       {   'points': 300,
                                                           'q': 'Durum (kesit) hikayeciliğinin Türk edebiyatındaki iki '
                                                                'büyük temsilcisi kimlerdir?',
                                                           'a': 'Sait Faik Abasıyanık ve Memduh Şevket Esendal',
                                                           'kaynak': 'MEB Edebiyat 9, s. 46',
                                                           'answered': False},
                                                       {   'points': 400,
                                                           'q': 'Tarihteki ilk yazılı Türkçe edebi metinler sayılan 8. '
                                                                'yüzyıla ait anıtlar hangileridir?',
                                                           'a': 'Orhun Abideleri (Göktürk Yazıtları)',
                                                           'kaynak': 'MEB Edebiyat 10, s. 22',
                                                           'answered': False}]},
                                  {   'id': 'tde_2',
                                      'name': 'Şiir Bilgisi & Nazım',
                                      'color': 'from-pink-700 to-purple-600',
                                      'badgeColor': 'text-pink-400 bg-pink-500/20 border-pink-500/40',
                                      'questions': [   {   'points': 100,
                                                           'q': 'Dize sonlarında görevleri aynı olan ses, ek veya '
                                                                'kelime tekrarlarına ne ad verilir?',
                                                           'a': 'Redif',
                                                           'kaynak': 'MEB Edebiyat 9, s. 68',
                                                           'answered': False},
                                                       {   'points': 200,
                                                           'q': 'Dize sonlarında tek bir ses benzerliğine dayanan '
                                                                'kafiye türüne ne ad verilir?',
                                                           'a': 'Yarım Kafiye',
                                                           'kaynak': 'MEB Edebiyat 9, s. 70',
                                                           'answered': False},
                                                       {   'points': 300,
                                                           'q': "Halk edebiyatında hece ölçüsüyle yazılan ve 11'li "
                                                                'kalıpla söylenen en yaygın nazım biçimi nedir?',
                                                           'a': 'Koşma',
                                                           'kaynak': 'MEB Edebiyat 10, s. 75',
                                                           'answered': False},
                                                       {   'points': 400,
                                                           'q': 'Divan edebiyatında aşk, şarap ve güzellik konularını '
                                                                "işleyen, ilk beyti 'matla' son beyti 'makta' olan "
                                                                'nazım şekli nedir?',
                                                           'a': 'Gazel',
                                                           'kaynak': 'MEB Edebiyat 10, s. 92',
                                                           'answered': False}]},
                                  {   'id': 'tde_3',
                                      'name': 'Söz Sanatları (Edebi Sanatlar)',
                                      'color': 'from-rose-600 to-pink-600',
                                      'badgeColor': 'text-rose-400 bg-rose-500/20 border-rose-500/40',
                                      'questions': [   {   'points': 100,
                                                           'q': 'Aralarında benzerlik ilişkisi kurularak zayıf olanın '
                                                                'güçlü olana benzetilmesi sanatına ne denir?',
                                                           'a': 'Teşbih (Benzetme)',
                                                           'kaynak': 'MEB Edebiyat 9, s. 84',
                                                           'answered': False},
                                                       {   'points': 200,
                                                           'q': 'İnsan dışındaki canlı veya cansız varlıklara insani '
                                                                'özellikler yükleme sanatına ne denir?',
                                                           'a': 'Teşhis (Kişileştirme)',
                                                           'kaynak': 'MEB Edebiyat 9, s. 86',
                                                           'answered': False},
                                                       {   'points': 300,
                                                           'q': 'Bir duyguyu veya durumu olduğundan çok daha fazla '
                                                                'veya az gösterme sanatına ne denir?',
                                                           'a': 'Mübalağa (Abartma)',
                                                           'kaynak': 'MEB Edebiyat 9, s. 88',
                                                           'answered': False},
                                                       {   'points': 400,
                                                           'q': 'Anlamca birbirine zıt iki kavramın veya düşüncenin '
                                                                'bir arada kullanılması sanatına ne ad verilir?',
                                                           'a': 'Tezat (Karşıtlık)',
                                                           'kaynak': 'MEB Edebiyat 9, s. 90',
                                                           'answered': False}]},
                                  {   'id': 'tde_4',
                                      'name': 'Dil Bilgisi & Yazım',
                                      'color': 'from-indigo-600 to-blue-600',
                                      'badgeColor': 'text-indigo-400 bg-indigo-500/20 border-indigo-500/40',
                                      'questions': [   {   'points': 100,
                                                           'q': "'Kitap - Kitabı' örneğinde görülen p harfinin b "
                                                                'harfine dönüşmesi hangi ses olayıdır?',
                                                           'a': 'Ünsüz Yumuşaması (Değişimi)',
                                                           'kaynak': 'MEB Edebiyat 9, s. 112',
                                                           'answered': False},
                                                       {   'points': 200,
                                                           'q': "Cümlede yükleme sorulan 'Kim?' veya 'Ne?' sorusu "
                                                                'öncelikle hangi cümlenin öğesini buldurur?',
                                                           'a': 'Özne',
                                                           'kaynak': 'MEB Edebiyat 9, s. 125',
                                                           'answered': False},
                                                       {   'points': 300,
                                                           'q': 'Bilinmeyen veya şüpheyle yaklaşılan bir bilgi/tarih '
                                                                'belirtilirken parantez içinde hangi noktalama işareti '
                                                                'kullanılır?',
                                                           'a': 'Soru İşareti (?)',
                                                           'kaynak': 'MEB Edebiyat 9, s. 140',
                                                           'answered': False},
                                                       {   'points': 400,
                                                           'q': "'Göz gezdirmek' deyiminin anlamı nedir?",
                                                           'a': 'Derinlemesine incelemeden kısaca bakmak',
                                                           'kaynak': 'MEB Edebiyat 9, s. 155',
                                                           'answered': False}]}],
    'din kültürü ve ahlak bilgisi': [   {   'id': 'din_1',
                                            'name': 'İnanç Esasları & Tevhid',
                                            'color': 'from-emerald-700 to-teal-600',
                                            'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
                                            'questions': [   {   'points': 100,
                                                                 'q': "İslam'ın temelini oluşturan, Allah'ın birliğine "
                                                                      've tekliğine inanma esasına ne ad verilir?',
                                                                 'a': 'Tevhid',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 24',
                                                                 'answered': False},
                                                             {   'points': 200,
                                                                 'q': "Allah'ın evrendeki her şeyi bir ölçü, düzen ve "
                                                                      'uyum içinde takdir edip planlamasına ne denir?',
                                                                 'a': 'Kader',
                                                                 'kaynak': 'MEB Din Kültürü 10, s. 38',
                                                                 'answered': False},
                                                             {   'points': 300,
                                                                 'q': 'Peygamberlerin doğru, dürüst ve asla yalan '
                                                                      'söylemeyen kimseler olduğunu ifade eden '
                                                                      'sıfatları hangisidir?',
                                                                 'a': 'Sıdk',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 52',
                                                                 'answered': False},
                                                             {   'points': 400,
                                                                 'q': 'Bir amaca ulaşmak için gerekli tüm tedbirleri '
                                                                      "aldıktan sonra sonucu Allah'a bırakıp güvenmeye "
                                                                      'ne denir?',
                                                                 'a': 'Tevekkül',
                                                                 'kaynak': 'MEB Din Kültürü 10, s. 42',
                                                                 'answered': False}]},
                                        {   'id': 'din_2',
                                            'name': 'İbadetler & Paylaşma',
                                            'color': 'from-teal-700 to-cyan-600',
                                            'badgeColor': 'text-teal-400 bg-teal-500/20 border-teal-500/40',
                                            'questions': [   {   'points': 100,
                                                                 'q': 'Dinen zengin sayılan Müslümanların yılda bir '
                                                                      "kez mallarının 1/40'ını (%2.5) ihtiyaç "
                                                                      'sahiplerine vermesi nedir?',
                                                                 'a': 'Zekat',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 86',
                                                                 'answered': False},
                                                             {   'points': 200,
                                                                 'q': 'Ramazan ayında oruca başlama vakti olan, tan '
                                                                      'yerinin ağarmasıyla imsak vaktine ne denir?',
                                                                 'a': 'İmsak',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 92',
                                                                 'answered': False},
                                                             {   'points': 300,
                                                                 'q': 'Haccın farzlarından biri olan, Kurban Bayramı '
                                                                      'arefe günü Arafat bölgesinde bir süre bulunmaya '
                                                                      'ne denir?',
                                                                 'a': 'Vakfe',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 104',
                                                                 'answered': False},
                                                             {   'points': 400,
                                                                 'q': 'İnsanın ölümünden sonra da sevabı devam eden '
                                                                      'cami, okul, çeşme gibi kalıcı hayır eserlerine '
                                                                      'ne ad verilir?',
                                                                 'a': 'Sadaka-i Cariye',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 88',
                                                                 'answered': False}]},
                                        {   'id': 'din_3',
                                            'name': "Kur'an & Peygamberimiz",
                                            'color': 'from-cyan-700 to-blue-600',
                                            'badgeColor': 'text-cyan-400 bg-cyan-500/20 border-cyan-500/40',
                                            'questions': [   {   'points': 100,
                                                                 'q': "Kur'an-ı Kerim'in Hz. Muhammed'e indirilmeye "
                                                                      'başlandığı 610 yılındaki mübarek gece '
                                                                      'hangisidir?',
                                                                 'a': 'Kadir Gecesi',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 44',
                                                                 'answered': False},
                                                             {   'points': 200,
                                                                 'q': "Hz. Peygamber'e Hira Mağarası'nda vahyedilen "
                                                                      'Alak suresinin ilk emri nedir?',
                                                                 'a': 'Oku! (İkra)',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 42',
                                                                 'answered': False},
                                                             {   'points': 300,
                                                                 'q': "Hz. Muhammed'in (s.a.v.) 632 yılında hac "
                                                                      'sırasında evrensel insan hakları ilkelerini '
                                                                      'ilan ettiği hitabesi nedir?',
                                                                 'a': 'Veda Hutbesi',
                                                                 'kaynak': 'MEB Din Kültürü 10, s. 95',
                                                                 'answered': False},
                                                             {   'points': 400,
                                                                 'q': "Müslümanların 622 yılında Mekke'den Medine'ye "
                                                                      'göç etmesine ve Hicri takvimin başlangıcı '
                                                                      'sayılan olaya ne denir?',
                                                                 'a': 'Hicret',
                                                                 'kaynak': 'MEB Din Kültürü 9, s. 60',
                                                                 'answered': False}]},
                                        {   'id': 'din_4',
                                            'name': 'Ahlak & Tasavvuf',
                                            'color': 'from-blue-700 to-indigo-600',
                                            'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                                            'questions': [   {   'points': 100,
                                                                 'q': 'Yapılan ibadet ve iyiliklerin yalnızca Allah '
                                                                      'rızası gözetilerek, gösterişten uzak '
                                                                      'yapılmasına ne ad verilir?',
                                                                 'a': 'İhlas',
                                                                 'kaynak': 'MEB Din Kültürü 10, s. 68',
                                                                 'answered': False},
                                                             {   'points': 200,
                                                                 'q': 'Bir kimsenin arkasından hoşlanmayacağı doğru '
                                                                      'kusurlarını konuşarak onu çekiştirmeye ne ad '
                                                                      'verilir?',
                                                                 'a': 'Gıybet',
                                                                 'kaynak': 'MEB Din Kültürü 10, s. 74',
                                                                 'answered': False},
                                                             {   'points': 300,
                                                                 'q': "'Yaratılanı severiz, Yaratandan ötürü' sözüyle "
                                                                      'sevgi ve hoşgörüyü anlatan büyük Türk '
                                                                      'mutasavvıfı kimdir?',
                                                                 'a': 'Yunus Emre',
                                                                 'kaynak': 'MEB Din Kültürü 12, s. 84',
                                                                 'answered': False},
                                                             {   'points': 400,
                                                                 'q': 'İsrafil (a.s.) tarafından Sûr borusuna ikinci '
                                                                      'kez üflenmesiyle insanların yeniden '
                                                                      'diriltilmesine ne denir?',
                                                                 'a': "Ba's (Diriliş)",
                                                                 'kaynak': 'MEB Din Kültürü 11, s. 22',
                                                                 'answered': False}]}],
    'fizik': [   {   'id': 'fiz_1',
                     'name': 'Kuvvet & Hareket',
                     'color': 'from-blue-600 to-indigo-600',
                     'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Bir cisme etki eden net kuvvet sıfır ise cismin mevcut durumunu '
                                               'korumasına ne denir?',
                                          'a': 'Eylemsizlik Prensibi',
                                          'kaynak': 'MEB Fizik 9, s. 138',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "F = m · a formülü Newton'un kaçıncı temel hareket yasasıdır?",
                                          'a': '2. Hareket Yasası (Temel Prensip)',
                                          'kaynak': 'MEB Fizik 9, s. 145',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Birim zamanda yapılan işe veya aktarılan enerji miktarına ne ad '
                                               'verilir?',
                                          'a': 'Güç (Birim: Watt)',
                                          'kaynak': 'MEB Fizik 9, s. 176',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Yerden h yüksekliğindeki m kütleli bir cismin sahip olduğu çekim '
                                               'potansiyel enerjisi formülü nedir?',
                                          'a': 'Ep = m · g · h',
                                          'kaynak': 'MEB Fizik 9, s. 182',
                                          'answered': False}]},
                 {   'id': 'fiz_2',
                     'name': 'Elektrik & Manyetizma',
                     'color': 'from-amber-600 to-yellow-600',
                     'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Bir iletkenin iki ucu arasındaki potansiyel farkının akıma oranını '
                                               'veren V = I · R bağıntısı nedir?',
                                          'a': 'Ohm Yasası',
                                          'kaynak': 'MEB Fizik 10, s. 22',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'SI birim sisteminde elektriksel yük birimi nedir?',
                                          'a': 'Coulomb (Klon)',
                                          'kaynak': 'MEB Fizik 9, s. 210',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Doğal veya yapay mıknatısların çevrelerinde oluşturduğu çekim alanına '
                                               'ne denir?',
                                          'a': 'Manyetik Alan',
                                          'kaynak': 'MEB Fizik 10, s. 68',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Manyetik akı değişimi sonucunda iletken bir telde elektrik akımı '
                                               'oluşmasına ne ad verilir?',
                                          'a': 'Elektromanyetik İndüksiyon',
                                          'kaynak': 'MEB Fizik 11, s. 280',
                                          'answered': False}]},
                 {   'id': 'fiz_3',
                     'name': 'Optik & Dalgalar',
                     'color': 'from-cyan-600 to-teal-600',
                     'badgeColor': 'text-cyan-400 bg-cyan-500/20 border-cyan-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Işığın boşluktaki yayılma hızı yaklaşık olarak saniyede kaç '
                                               'kilometredir?',
                                          'a': '300.000 km/s (3×10⁸ m/s)',
                                          'kaynak': 'MEB Fizik 10, s. 190',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Işığın bir saydam ortamdan diğerine geçerken hız ve doğrultu '
                                               'değiştirmesine ne denir?',
                                          'a': 'Işığın Kırılması (Refraksiyon)',
                                          'kaynak': 'MEB Fizik 10, s. 224',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Ses dalgaları maddesel olmayan bir ortamda (boşlukta) yayılabilir mi?',
                                          'a': 'Hayır, mekanik dalgadır, maddesel ortam şarttır',
                                          'kaynak': 'MEB Fizik 10, s. 154',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Üzerine gelen paralel ışık ışınlarını odak noktasında toplayan mercek '
                                               'türü hangisidir?',
                                          'a': 'İnce Kenarlı (Yakınsak) Mercek',
                                          'kaynak': 'MEB Fizik 10, s. 248',
                                          'answered': False}]},
                 {   'id': 'fiz_4',
                     'name': 'Termodinamik & Madde',
                     'color': 'from-rose-600 to-red-600',
                     'badgeColor': 'text-rose-400 bg-rose-500/20 border-rose-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Bir maddedeki moleküllerin ortalama kinetik enerjisinin ölçüsü olan '
                                               'büyüklük nedir?',
                                          'a': 'Sıcaklık (Birim: Kelvin / °C)',
                                          'kaynak': 'MEB Fizik 9, s. 98',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Sıcaklıkları farklı iki madde arasında temas sonucu aktarılan enerjiye '
                                               'ne ad verilir?',
                                          'a': 'Isı Enerjisi (Joule / Kalori)',
                                          'kaynak': 'MEB Fizik 9, s. 104',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Bir maddenin katı halden sıvılaşmadan doğrudan gaz haline geçmesi '
                                               'olayına ne denir?',
                                          'a': 'Süblimleşme',
                                          'kaynak': 'MEB Fizik 9, s. 116',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Isının boşlukta herhangi bir aracı tanecik olmadan elektromanyetik '
                                               'dalgalarla yayılmasına ne denir?',
                                          'a': 'Işıma (Radyasyon)',
                                          'kaynak': 'MEB Fizik 9, s. 128',
                                          'answered': False}]}],
    'cografya': [   {   'id': 'cog_1',
                        'name': 'Doğal Sistemler & İklim',
                        'color': 'from-emerald-600 to-teal-600',
                        'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Hava olaylarının (yağmur, kar, rüzgar) tamamının gerçekleştiği '
                                                  'atmosfer katmanı hangisidir?',
                                             'a': 'Troposfer',
                                             'kaynak': 'MEB Coğrafya 9, s. 88',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'Yazları sıcak-kurak, kışları ılık-yağışlı geçen ve maki bitki '
                                                  'örtüsüne sahip iklim hangisidir?',
                                             'a': 'Akdeniz İklimi',
                                             'kaynak': 'MEB Coğrafya 9, s. 122',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': "Kuzey Yarımküre'de Dünya'nın kendi ekseni etrafında dönmesi sonucu "
                                                  'rüzgarlar hangi yöne sapar?',
                                             'a': 'Sağa doğru',
                                             'kaynak': 'MEB Coğrafya 9, s. 102',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': '21 Mart ve 23 Eylül tarihlerinde yaşanan gece ve gündüz sürelerinin '
                                                  'eşitliğine ne denir?',
                                             'a': 'Ekinoks',
                                             'kaynak': 'MEB Coğrafya 9, s. 28',
                                             'answered': False}]},
                    {   'id': 'cog_2',
                        'name': 'Harita & Koordinatlar',
                        'color': 'from-blue-600 to-cyan-600',
                        'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Topografya haritalarında deniz seviyesinden yükseltisi eşit '
                                                  'noktaları birleştiren eğrilere ne denir?',
                                             'a': 'İzohips (Eş Yükselti Eğrisi)',
                                             'kaynak': 'MEB Coğrafya 9, s. 54',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'Ardışık iki meridyen arasındaki yerel saat farkı kaç dakikadır?',
                                             'a': '4 Dakika',
                                             'kaynak': 'MEB Coğrafya 9, s. 34',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': '1/200.000 ölçekli bir haritada 1 cm gerçekte kaç kilometreyi '
                                                  'gösterir?',
                                             'a': '2 Kilometre',
                                             'kaynak': 'MEB Coğrafya 9, s. 46',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': "Dünya'nın kutuplardan basık, ekvatordan şişkin kendine özgü "
                                                  'geometrik şekline ne ad verilir?',
                                             'a': 'Geoit',
                                             'kaynak': 'MEB Coğrafya 9, s. 20',
                                             'answered': False}]},
                    {   'id': 'cog_3',
                        'name': 'Türkiye Coğrafyası',
                        'color': 'from-teal-600 to-green-600',
                        'badgeColor': 'text-teal-400 bg-teal-500/20 border-teal-500/40',
                        'questions': [   {   'points': 100,
                                             'q': "Türkiye'nin yüz ölçümü bakımından en büyük gölü hangisidir?",
                                             'a': 'Van Gölü',
                                             'kaynak': 'MEB Coğrafya 10, s. 68',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': "Türkiye'nin volkanik patlamalarla oluşan en yüksek zirvesi "
                                                  'hangisidir?',
                                             'a': 'Ağrı Dağı (5137 m)',
                                             'kaynak': 'MEB Coğrafya 10, s. 42',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Akarsuların taşıdığı alüvyonları denize döküldükleri kıyılarda '
                                                  'biriktirmesiyle oluşan ovaya ne denir?',
                                             'a': 'Delta Ovası',
                                             'kaynak': 'MEB Coğrafya 10, s. 52',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Türkiye hangi paralel (enlem) ve meridyen (boylam) aralığında yer '
                                                  'almaktadır?',
                                             'a': '36°-42° Kuzey / 26°-45° Doğu',
                                             'kaynak': 'MEB Coğrafya 9, s. 38',
                                             'answered': False}]},
                    {   'id': 'cog_4',
                        'name': 'Beşeri Sistemler & Çevre',
                        'color': 'from-amber-600 to-orange-600',
                        'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Tabanı geniş üçgen şeklindeki nüfus piramidi bir ülkenin hangi '
                                                  'özelliğini gösterir?',
                                             'a': 'Doğum oranının yüksek olduğunu',
                                             'kaynak': 'MEB Coğrafya 10, s. 168',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': "Akdeniz'i Kızıldeniz'e bağlayan insan yapımı stratejik su yolu "
                                                  'hangisidir?',
                                             'a': 'Süveyş Kanalı',
                                             'kaynak': 'MEB Coğrafya 11, s. 182',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Üst verimli toprak tabakasının rüzgar ve sularla aşınıp taşınması '
                                                  'olayına ne denir?',
                                             'a': 'Erozyon',
                                             'kaynak': 'MEB Coğrafya 10, s. 94',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Bir kilometrekareye düşen insan sayısını ifade eden nüfus yoğunluğu '
                                                  'türü nedir?',
                                             'a': 'Aritmetik Nüfus Yoğunluğu',
                                             'kaynak': 'MEB Coğrafya 10, s. 172',
                                             'answered': False}]}],
    'felsefe': [   {   'id': 'fel_1',
                       'name': 'Felsefeye Giriş & Düşünme',
                       'color': 'from-purple-600 to-indigo-600',
                       'badgeColor': 'text-purple-400 bg-purple-500/20 border-purple-500/40',
                       'questions': [   {   'points': 100,
                                            'q': 'Felsefe (Philosophia) kelimesinin kökeni ve Türkçe karşılığı nedir?',
                                            'a': 'Bilgelik Sevgisi (Hikmet Arayışı)',
                                            'kaynak': 'MEB Felsefe 10, s. 14',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': 'Felsefe tarihinin ilk filozofu kabul edilen ve arkhe olarak suyu '
                                                 'gören düşünür kimdir?',
                                            'a': 'Thales',
                                            'kaynak': 'MEB Felsefe 11, s. 18',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': "Sokrates'in zihindeki doğuştan bilgileri soru-cevapla açığa çıkarma "
                                                 'yöntemine ne denir?',
                                            'a': 'Maiotik (Doğurtma Yöntemi)',
                                            'kaynak': 'MEB Felsefe 11, s. 32',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': "'Bir şey ne ise odur (A, A'dır)' ilkesi klasik mantığın hangi temel "
                                                 'ilkesidir?',
                                            'a': 'Özdeşlik İlkesi',
                                            'kaynak': 'MEB Mantık 10, s. 24',
                                            'answered': False}]},
                   {   'id': 'fel_2',
                       'name': 'Bilgi & Varlık Felsefesi',
                       'color': 'from-indigo-600 to-blue-600',
                       'badgeColor': 'text-indigo-400 bg-indigo-500/20 border-indigo-500/40',
                       'questions': [   {   'points': 100,
                                            'q': 'Doğru bilginin kaynağını yalnızca akılda gören felsefi akım '
                                                 'hangisidir?',
                                            'a': 'Rasyonalizm (Akılcılık)',
                                            'kaynak': 'MEB Felsefe 10, s. 54',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': 'İnsan zihninin doğuştan boş bir levha (Tabula Rasa) olduğunu savunan '
                                                 'empirist filozof kimdir?',
                                            'a': 'John Locke',
                                            'kaynak': 'MEB Felsefe 11, s. 92',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': 'Varlığın temelinde maddeyi gören felsefi görüş hangisidir?',
                                            'a': 'Materyalizm',
                                            'kaynak': 'MEB Felsefe 10, s. 78',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': "'Düşünüyorum, öyleyse varım' diyerek metodik şüpheyi kullanan "
                                                 'düşünür kimdir?',
                                            'a': 'René Descartes',
                                            'kaynak': 'MEB Felsefe 11, s. 86',
                                            'answered': False}]},
                   {   'id': 'fel_3',
                       'name': 'Ahlak & Siyaset Felsefesi',
                       'color': 'from-violet-600 to-purple-600',
                       'badgeColor': 'text-violet-400 bg-violet-500/20 border-violet-500/40',
                       'questions': [   {   'points': 100,
                                            'q': "Kant'ın hiçbir şarta ve çıkara bağlı olmayan evrensel ahlak ilkesine "
                                                 'ne denir?',
                                            'a': 'Ödev Ahlakı (Kategorik Buyruk)',
                                            'kaynak': 'MEB Felsefe 11, s. 112',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': 'Gerçekte var olmayan ancak ideal bir toplum ve devlet düzenini '
                                                 'tasarlayan metinlere ne denir?',
                                            'a': 'Ütopya',
                                            'kaynak': 'MEB Felsefe 10, s. 138',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': "İslam filozofu Farabi'nin ideal ve erdemli toplumu anlattığı "
                                                 'başyapıtı hangisidir?',
                                            'a': "El-Medinetü'l-Fazıla",
                                            'kaynak': 'MEB Felsefe 11, s. 64',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': "Aristoteles'in ahlakta iki aşırılık arasındaki ölçülülüğü önerdiği "
                                                 'kavram nedir?',
                                            'a': 'Altın Orta İlkesi',
                                            'kaynak': 'MEB Felsefe 11, s. 46',
                                            'answered': False}]},
                   {   'id': 'fel_4',
                       'name': 'Sanat & Bilim Felsefesi',
                       'color': 'from-pink-600 to-rose-600',
                       'badgeColor': 'text-pink-400 bg-pink-500/20 border-pink-500/40',
                       'questions': [   {   'points': 100,
                                            'q': 'Sanatı, güzelliği ve estetik değerleri inceleyen felsefe dalı '
                                                 'hangisidir?',
                                            'a': 'Estetik (Sanat Felsefesi)',
                                            'kaynak': 'MEB Felsefe 10, s. 156',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': "Platon'un duyular dünyası ile akılla kavranan dünyayı ayıran ünlü "
                                                 'alegorisi nedir?',
                                            'a': 'Mağara Alegorisi',
                                            'kaynak': 'MEB Felsefe 11, s. 38',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': 'Yalnızca deney ve gözlemle doğrulanabilen olguları gerçek sayan '
                                                 'pozitivizmin kurucusu kimdir?',
                                            'a': 'Auguste Comte',
                                            'kaynak': 'MEB Felsefe 11, s. 128',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': 'Evrenin anlamsız olduğunu ve hiçbir değerin temeli olmadığını '
                                                 'savunan akım hangisidir?',
                                            'a': 'Nihilizm (Hiççilik)',
                                            'kaynak': 'MEB Felsefe 10, s. 82',
                                            'answered': False}]}],
    'almanca': [
        {'id': 'alm_1', 'name': 'Zahlen & Farben', 'color': 'from-yellow-600 to-amber-600', 'badgeColor': 'text-yellow-400 bg-yellow-500/20 border-yellow-500/40',
         'questions': [
            {'points': 100, 'q': "'Drei' kelimesinin Almanca yazılışı nedir?", 'a': 'drei', 'kaynak': 'MEB Almanca A1, s. 11', 'answered': False},
            {'points': 200, 'q': "Almanca 'blau' hangi rengin adıdır?", 'a': 'Mavi', 'kaynak': 'MEB Almanca A1, s. 12', 'answered': False},
            {'points': 300, 'q': "'Zwanzig' sayısı kaçtır?", 'a': '20', 'kaynak': 'MEB Almanca A1, s. 13', 'answered': False},
            {'points': 400, 'q': "Almanca 'achtzehn' sayısı kaçtır?", 'a': '18', 'kaynak': 'MEB Almanca A1, s. 14', 'answered': False},
        ]},
        {'id': 'alm_2', 'name': 'Artikel & Nomen', 'color': 'from-sky-600 to-blue-600', 'badgeColor': 'text-sky-400 bg-sky-500/20 border-sky-500/40',
         'questions': [
            {'points': 100, 'q': "'Haus' (ev) isminin belirli tanımlığı (Artikel) nedir?", 'a': 'das', 'kaynak': 'MEB Almanca A1, s. 21', 'answered': False},
            {'points': 200, 'q': "'Tisch' (masa) isminin belirli tanımlığı nedir?", 'a': 'der', 'kaynak': 'MEB Almanca A1, s. 22', 'answered': False},
            {'points': 300, 'q': "'Schule' (okul) isminin belirli tanımlığı nedir?", 'a': 'die', 'kaynak': 'MEB Almanca A1, s. 23', 'answered': False},
            {'points': 400, 'q': "'Kind' kelimesinin çoğul hali nedir?", 'a': 'Kinder', 'kaynak': 'MEB Almanca A2, s. 24', 'answered': False},
        ]},
        {'id': 'alm_3', 'name': 'Verben', 'color': 'from-emerald-600 to-teal-600', 'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
         'questions': [
            {'points': 100, 'q': "'Ich ____ Schüler.' boşluğuna 'sein' fiilinin doğru hali gelir?", 'a': 'bin', 'kaynak': 'MEB Almanca A1, s. 31', 'answered': False},
            {'points': 200, 'q': "'Er ____ Fußball.' (spielen) boşluğuna ne gelir?", 'a': 'spielt', 'kaynak': 'MEB Almanca A1, s. 32', 'answered': False},
            {'points': 300, 'q': "'Wir ____ nach Hause.' (gehen) boşluğuna ne gelir?", 'a': 'gehen', 'kaynak': 'MEB Almanca A1, s. 33', 'answered': False},
            {'points': 400, 'q': "'haben' fiilinin 'du' ile çekimi nedir?", 'a': 'hast', 'kaynak': 'MEB Almanca A1, s. 34', 'answered': False},
        ]},
        {'id': 'alm_4', 'name': 'Alltag & Fragen', 'color': 'from-purple-600 to-pink-600', 'badgeColor': 'text-purple-400 bg-purple-500/20 border-purple-500/40',
         'questions': [
            {'points': 100, 'q': "'Guten Morgen' ne anlama gelir?", 'a': 'Günaydın', 'kaynak': 'MEB Almanca A1, s. 41', 'answered': False},
            {'points': 200, 'q': "'Wie heißt du?' ne anlama gelir?", 'a': 'Adın ne?', 'kaynak': 'MEB Almanca A1, s. 42', 'answered': False},
            {'points': 300, 'q': "'Wo wohnst du?' sorusunun Türkçesi nedir?", 'a': 'Nerede oturuyorsun?', 'kaynak': 'MEB Almanca A1, s. 43', 'answered': False},
            {'points': 400, 'q': "'Danke schön' karşılığında söylenen 'rica ederim' Almanca nedir?", 'a': 'Bitte schön', 'kaynak': 'MEB Almanca A1, s. 44', 'answered': False},
        ]},
    ],
    'ingilizce': [   {   'id': 'ing_1',
                         'name': 'Grammar & Tenses',
                         'color': 'from-sky-600 to-blue-600',
                         'badgeColor': 'text-sky-400 bg-sky-500/20 border-sky-500/40',
                         'questions': [   {   'points': 100,
                                              'q': "'She has lived in Ankara ____ 2018.' boşluğuna hangi edat "
                                                   'gelmelidir?',
                                              'a': 'since',
                                              'kaynak': 'MEB English 10, p. 34',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': "'If I had wings, I ____ fly to the moon.' cümlesinde hangi "
                                                   'yardımcı fiil kullanılır?',
                                              'a': 'would',
                                              'kaynak': 'MEB English 10, p. 78',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': "'The car was washed ____ my father.' cümlesinde eylemi yapanı "
                                                   'belirten edat nedir?',
                                              'a': 'by',
                                              'kaynak': 'MEB English 11, p. 52',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': "'The student ____ won the competition is my friend.' cümlesine "
                                                   'insanı niteleyen hangi bağlaç gelir?',
                                              'a': 'who',
                                              'kaynak': 'MEB English 11, p. 88',
                                              'answered': False}]},
                     {   'id': 'ing_2',
                         'name': 'Vocabulary & Opposites',
                         'color': 'from-teal-600 to-emerald-600',
                         'badgeColor': 'text-teal-400 bg-teal-500/20 border-teal-500/40',
                         'questions': [   {   'points': 100,
                                              'q': "'Ancient' (antik/eski) kelimesinin zıt anlamlısı nedir?",
                                              'a': 'Modern',
                                              'kaynak': 'MEB English 9, p. 82',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': "'Huge' kelimesinin eş anlamlısı (synonym) hangisidir?",
                                              'a': 'Enormous / Giant',
                                              'kaynak': 'MEB English 9, p. 64',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': "'Global warming' kavramının Türkçe karşılığı nedir?",
                                              'a': 'Küresel Isınma',
                                              'kaynak': 'MEB English 10, p. 96',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': "'Pollution' kelimesinin Türkçe anlamı nedir?",
                                              'a': 'Kirlilik (Çevre/Hava)',
                                              'kaynak': 'MEB English 10, p. 98',
                                              'answered': False}]},
                     {   'id': 'ing_3',
                         'name': 'Phrasal Verbs & Idioms',
                         'color': 'from-amber-600 to-orange-600',
                         'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                         'questions': [   {   'points': 100,
                                              'q': "'Give up' deyimsel fiilinin Türkçe anlamı nedir?",
                                              'a': 'Vazgeçmek / Bırakmak',
                                              'kaynak': 'MEB English 10, p. 120',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': "'Look forward to' ifadesi ne anlama gelir?",
                                              'a': 'Dört gözle beklemek',
                                              'kaynak': 'MEB English 11, p. 40',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': "İngilizcede 'Piece of cake' deyimi ne ifade eder?",
                                              'a': 'Çok kolay / Çocuk oyuncağı',
                                              'kaynak': 'MEB English 11, p. 104',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': "'Turn off' komutu elektronik bir cihaz için ne anlama gelir?",
                                              'a': 'Kapatmak (cihazı durdurmak)',
                                              'kaynak': 'MEB English 9, p. 110',
                                              'answered': False}]},
                     {   'id': 'ing_4',
                         'name': 'Everyday English',
                         'color': 'from-rose-600 to-pink-600',
                         'badgeColor': 'text-rose-400 bg-rose-500/20 border-rose-500/40',
                         'questions': [   {   'points': 100,
                                              'q': 'Bir şeyin fiyatını sorarken hangi soru kalıbı kullanılır?',
                                              'a': 'How much is it?',
                                              'kaynak': 'MEB English 9, p. 30',
                                              'answered': False},
                                          {   'points': 200,
                                              'q': "'Could you please open the window?' ifadesi hangi iletişim "
                                                   'fonksiyonudur?',
                                              'a': 'Kibarca ricada bulunma (Polite Request)',
                                              'kaynak': 'MEB English 9, p. 45',
                                              'answered': False},
                                          {   'points': 300,
                                              'q': "'You are ready, ____?' cümlesinin doğru soru takısı (question tag) "
                                                   'nedir?',
                                              'a': "aren't you?",
                                              'kaynak': 'MEB English 11, p. 64',
                                              'answered': False},
                                          {   'points': 400,
                                              'q': 'Geçmişte düzenli yapılıp artık terkedilmiş alışkanlıkları anlatan '
                                                   'yapı nedir?',
                                              'a': 'Used to',
                                              'kaynak': 'MEB English 10, p. 44',
                                              'answered': False}]}],
    'bilisim': [   {   'id': 'bil_1',
                       'name': 'Algoritma & Programlama',
                       'color': 'from-cyan-600 to-blue-600',
                       'badgeColor': 'text-cyan-400 bg-cyan-500/20 border-cyan-500/40',
                       'questions': [   {   'points': 100,
                                            'q': 'Bir problemin çözümüne adım adım ulaştıran sonlu mantık kuralları '
                                                 'dizisine ne denir?',
                                            'a': 'Algoritma',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 42',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': 'Python programlama dilinde metinsel veri tipinin kısaltması nedir?',
                                            'a': 'str (string)',
                                            'kaynak': 'MEB Bilgisayar Bilimi, s. 52',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': 'Belirli bir kod bloğunu belirli sayıda tekrar çalıştırmak için hangi '
                                                 'döngü yapısı kullanılır?',
                                            'a': 'for döngüsü',
                                            'kaynak': 'MEB Bilgisayar Bilimi, s. 78',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': 'İlişkisel veritabanlarını sorgulamak ve yönetmek için kullanılan dil '
                                                 'hangisidir?',
                                            'a': 'SQL',
                                            'kaynak': 'MEB Bilgisayar Bilimi, s. 154',
                                            'answered': False}]},
                   {   'id': 'bil_2',
                       'name': 'Donanım & Bellek',
                       'color': 'from-blue-600 to-indigo-600',
                       'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                       'questions': [   {   'points': 100,
                                            'q': 'Bilgisayarın tüm hesaplama ve komut yürütme işlemlerini yapan '
                                                 "'beyin' donanımı nedir?",
                                            'a': 'İşlemci (CPU)',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 18',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': 'Çalışan programların verilerini tutan ve elektrik kesildiğinde '
                                                 'sıfırlanan geçici bellek hangisidir?',
                                            'a': 'RAM Bellek',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 22',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': "1 Kilobayt (KB) kaç Bayt'tan oluşmaktadır?",
                                            'a': '1024 Bayt',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 26',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': 'Bilgisayarların verileri temsil etmek için kullandığı 0 ve 1 tabanlı '
                                                 'sayı sistemi nedir?',
                                            'a': 'İkili (Binary) Sayı Sistemi',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 28',
                                            'answered': False}]},
                   {   'id': 'bil_3',
                       'name': 'Ağlar & Siber Güvenlik',
                       'color': 'from-emerald-600 to-teal-600',
                       'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
                       'questions': [   {   'points': 100,
                                            'q': 'Ağa bağlı her cihazın internette tanınmasını sağlayan benzersiz '
                                                 'sayısal adrese ne denir?',
                                            'a': 'IP Adresi',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 116',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': 'Gelen ve giden ağ trafiğini denetleyerek yetkisiz erişimleri '
                                                 'engelleyen güvenlik sistemi nedir?',
                                            'a': 'Güvenlik Duvarı (Firewall)',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 142',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': 'Verilerin yetkisiz okunmasını engellemek için algoritmalarla '
                                                 'dönüştürülmesine ne ad verilir?',
                                            'a': 'Kriptografi (Şifreleme)',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 138',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': 'Alan adlarını (örn. farabi.local) IP adreslerine dönüştüren sistem '
                                                 'hangisidir?',
                                            'a': 'DNS (Domain Name System)',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 120',
                                            'answered': False}]},
                   {   'id': 'bil_4',
                       'name': 'Modern Bilişim & Yapay Zeka',
                       'color': 'from-purple-600 to-pink-600',
                       'badgeColor': 'text-purple-400 bg-purple-500/20 border-purple-500/40',
                       'questions': [   {   'points': 100,
                                            'q': 'Milli Eğitim Bakanlığı akıllı tahtalarında kullanılan yerli Linux '
                                                 'işletim sistemi nedir?',
                                            'a': 'Pardus (ETAP)',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 64',
                                            'answered': False},
                                        {   'points': 200,
                                            'q': 'Kaynak kodları herkesin incelemesine, geliştirmesine ve paylaşmasına '
                                                 'açık yazılımlara ne ad verilir?',
                                            'a': 'Açık Kaynak Kodlu Yazılım',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 48',
                                            'answered': False},
                                        {   'points': 300,
                                            'q': 'Bilgisayarların verilerden örüntüler öğrenerek tahmin üretmesini '
                                                 'sağlayan yapay zeka dalı nedir?',
                                            'a': 'Makine Öğrenimi (Machine Learning)',
                                            'kaynak': 'MEB Bilgisayar Bilimi, s. 192',
                                            'answered': False},
                                        {   'points': 400,
                                            'q': 'Verilerin yerel disk yerine internet üzerindeki uzak sunucularda '
                                                 'saklanması hizmetine ne denir?',
                                            'a': 'Bulut Bilişim (Cloud Computing)',
                                            'kaynak': 'MEB Bilişim Teknolojileri, s. 126',
                                            'answered': False}]}],
    'saglik': [   {   'id': 'sag_1',
                      'name': 'İlk Yardım & Müdahale',
                      'color': 'from-red-600 to-rose-600',
                      'badgeColor': 'text-red-400 bg-red-500/20 border-red-500/40',
                      'questions': [   {   'points': 100,
                                           'q': "Türkiye'de tüm acil yardım birimlerini tek çatıda toplayan çağrı "
                                                'numarası nedir?',
                                           'a': '112 Acil Çağrı',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 38',
                                           'answered': False},
                                       {   'points': 200,
                                           'q': 'Yetişkinlerde temel yaşam desteğinde kalp masajı ve suni solunum '
                                                'oranı kaçtır?',
                                           'a': '30 Kalp Masajı - 2 Suni Solunum',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 46',
                                           'answered': False},
                                       {   'points': 300,
                                           'q': 'Tam tıkanma yaşayan, nefes alamayan ve ellerini boğazına götüren '
                                                'kişiye hangi manevra uygulanır?',
                                           'a': 'Heimlich Manevrası',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 58',
                                           'answered': False},
                                       {   'points': 400,
                                           'q': 'Bilinci kapalı ancak solunumu ve nabzı olan kazazedeye hangi pozisyon '
                                                'verilir?',
                                           'a': 'Koma (Yan Yatış) Pozisyonu',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 52',
                                           'answered': False}]},
                  {   'id': 'sag_2',
                      'name': 'Trafik Kuralları & Güvenlik',
                      'color': 'from-amber-600 to-yellow-600',
                      'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                      'questions': [   {   'points': 100,
                                           'q': 'Kavşaklarda ve yaya geçitlerinde geçiş üstünlüğü öncelikle kime '
                                                'aittir?',
                                           'a': 'Yayaya',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 132',
                                           'answered': False},
                                       {   'points': 200,
                                           'q': 'Kavşakta karşılaşan araçlardan hangisinin geçiş üstünlüğü her zaman '
                                                'en önceliklidir?',
                                           'a': 'Ambulans (Cankurtaran)',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 128',
                                           'answered': False},
                                       {   'points': 300,
                                           'q': 'Eşkenar üçgen şeklindeki kırmızı kenarlı trafik işaret levhaları neyi '
                                                'bildirir?',
                                           'a': 'Tehlike Uyarı İşareti',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 118',
                                           'answered': False},
                                       {   'points': 400,
                                           'q': 'Kaza anında yolcuların araç dışına fırlamasını ve ön panele '
                                                'çarpmasını önleyen temel donanım nedir?',
                                           'a': 'Emniyet Kemeri',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 140',
                                           'answered': False}]},
                  {   'id': 'sag_3',
                      'name': 'Sağlıklı Yaşam & Beslenme',
                      'color': 'from-emerald-600 to-teal-600',
                      'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
                      'questions': [   {   'points': 100,
                                           'q': 'Yetişkin bir insanın sağlıklı metabolizma için günde ortalama kaç '
                                                'litre su tüketmesi önerilir?',
                                           'a': '2 - 2.5 Litre',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 86',
                                           'answered': False},
                                       {   'points': 200,
                                           'q': 'Vücut ağırlığının boyun karesine bölünmesiyle (kg/m²) hesaplanan '
                                                'obezite göstergesi nedir?',
                                           'a': 'Vücut Kitle İndeksi (VKİ)',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 82',
                                           'answered': False},
                                       {   'points': 300,
                                           'q': 'Vücuda zayıflatılmış mikroplar verilerek hastalığa karşı aktif '
                                                'bağışıklık sağlayan yöntem nedir?',
                                           'a': 'Aşı',
                                           'kaynak': 'MEB Sağlık Bilgisi ve Trafik 9, s. 94',
                                           'answered': False},
                                       {   'points': 400,
                                           'q': 'Sağlıklı bir yetişkinde dinlenme anındaki ortalama kalp atım (nabız) '
                                                'sayısı aralığı nedir?',
                                           'a': '60 - 100 atım/dakika',
                                           'kaynak': 'MEB Beden Eğitimi ve Spor, s. 36',
                                           'answered': False}]},
                  {   'id': 'sag_4',
                      'name': 'Spor Kültürü & Vücut',
                      'color': 'from-blue-600 to-cyan-600',
                      'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                      'questions': [   {   'points': 100,
                                           'q': 'Ağır spor aktivitelerinden önce kas zedelenmelerini önlemek için '
                                                'yapılan hazırlık çalışması nedir?',
                                           'a': 'Isınma ve Esneme (Stretching)',
                                           'kaynak': 'MEB Beden Eğitimi ve Spor, s. 28',
                                           'answered': False},
                                       {   'points': 200,
                                           'q': 'Voleybol maçında sahada aynı anda bir takımdan kaç oyuncu yer alır?',
                                           'a': '6 Oyuncu',
                                           'kaynak': 'MEB Beden Eğitimi ve Spor, s. 62',
                                           'answered': False},
                                       {   'points': 300,
                                           'q': 'Basketbolda top sürülmeden topla birlikte 2 adımdan fazla yürünmesi '
                                                'ihlaline ne ad verilir?',
                                           'a': 'Hatalı Yürüme (Steps)',
                                           'kaynak': 'MEB Beden Eğitimi ve Spor, s. 54',
                                           'answered': False},
                                       {   'points': 400,
                                           'q': 'İnsan iskeletinde vücudun en uzun ve en güçlü kemiği hangisidir?',
                                           'a': 'Uyluk Kemiği (Femur)',
                                           'kaynak': 'MEB Beden Eğitimi ve Spor, s. 40',
                                           'answered': False}]}],
    'sanat': [   {   'id': 'san_1',
                     'name': 'Görsel Sanatlar & Renk',
                     'color': 'from-rose-600 to-pink-600',
                     'badgeColor': 'text-rose-400 bg-rose-500/20 border-rose-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Resim sanatında diğer renklerin karışımıyla elde edilemeyen üç ana '
                                               'renk hangileridir?',
                                          'a': 'Kırmızı, Sarı, Mavi',
                                          'kaynak': 'MEB Görsel Sanatlar 9, s. 22',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Kırmızı ve sarı renklerin eşit oranda karışımıyla hangi ara renk elde '
                                               'edilir?',
                                          'a': 'Turuncu',
                                          'kaynak': 'MEB Görsel Sanatlar 9, s. 24',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': "Rönesans'ta geliştirilen ve üç boyutlu derinliği iki boyutlu yüzeyde "
                                               'gösteren çizim kuralı nedir?',
                                          'a': 'Perspektif',
                                          'kaynak': 'MEB Görsel Sanatlar 9, s. 36',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Nesneleri geometrik formlara ayırarak resmeden Kübizm akımının '
                                               'kurucusu İspanyol ressam kimdir?',
                                          'a': 'Pablo Picasso',
                                          'kaynak': 'MEB Görsel Sanatlar 12, s. 38',
                                          'answered': False}]},
                 {   'id': 'san_2',
                     'name': 'Geleneksel Türk Sanatları',
                     'color': 'from-amber-600 to-orange-600',
                     'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Kitreli su üzerine özel boyalar damlatılarak desen oluşturulan '
                                               'geleneksel Türk sanatı nedir?',
                                          'a': 'Ebru Sanatı',
                                          'kaynak': 'MEB Görsel Sanatlar 9, s. 88',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "Büyük mimar Sinan'ın 'Ustalık eserim' dediği Edirne'deki anıtsal cami "
                                               'hangisidir?',
                                          'a': 'Selimiye Camii',
                                          'kaynak': 'MEB Görsel Sanatlar 11, s. 72',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Yazma eserleri altın tozu ve boyalarla bezeme ve süsleme sanatına ne '
                                               'ad verilir?',
                                          'a': 'Tezhip (Altınlama)',
                                          'kaynak': 'MEB Görsel Sanatlar 10, s. 86',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': "Meşhur 'Kaplumbağa Terbiyecisi' tablosunun ressamı ve müzeci kimdir?",
                                          'a': 'Osman Hamdi Bey',
                                          'kaynak': 'MEB Görsel Sanatlar 11, s. 94',
                                          'answered': False}]},
                 {   'id': 'san_3',
                     'name': 'Müzik & Solfej Bilgisi',
                     'color': 'from-teal-600 to-cyan-600',
                     'badgeColor': 'text-teal-400 bg-teal-500/20 border-teal-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Porte üzerinde sol anahtarının başladığı ikinci çizgiye hangi nota '
                                               'yerleşir?',
                                          'a': 'Sol Notası',
                                          'kaynak': 'MEB Müzik 9, s. 18',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Müzikte notaların üzerine yazıldığı 5 paralel çizgi ve 4 aralıktan '
                                               'oluşan yapıya ne denir?',
                                          'a': 'Porte (Dizek)',
                                          'kaynak': 'MEB Müzik 9, s. 14',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Türk halk müziğinin en temel telli ve tezeneli geleneksel enstrümanı '
                                               'hangisidir?',
                                          'a': 'Bağlama (Saz)',
                                          'kaynak': 'MEB Müzik 9, s. 42',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'İstiklal Marşımızın bugün okunan resmi bestesini yapan ünlü Türk '
                                               'besteci kimdir?',
                                          'a': 'Osman Zeki Üngör',
                                          'kaynak': 'MEB Müzik 9, s. 28',
                                          'answered': False}]},
                 {   'id': 'san_4',
                     'name': 'Dünya Başyapıtları & Mimari',
                     'color': 'from-purple-600 to-indigo-600',
                     'badgeColor': 'text-purple-400 bg-purple-500/20 border-purple-500/40',
                     'questions': [   {   'points': 100,
                                          'q': "Leonardo da Vinci'nin Paris Louvre Müzesi'ndeki dünyaca ünlü portresi "
                                               'hangisidir?',
                                          'a': 'Mona Lisa',
                                          'kaynak': 'MEB Görsel Sanatlar 10, s. 64',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "Floransa'da bulunan ünlü 'Davut' (David) mermer heykelini yapan "
                                               'heykeltıraş kimdir?',
                                          'a': 'Michelangelo',
                                          'kaynak': 'MEB Görsel Sanatlar 10, s. 70',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': "Mozart'ın mehter marşı ezgilerinden esinlenerek bestelediği meşhur "
                                               'piyano eseri nedir?',
                                          'a': 'Türk Marşı (Rondo alla Turca)',
                                          'kaynak': 'MEB Müzik 10, s. 68',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': "Işık ve rengin anlık etkilerini tuvale yansıtan Claude Monet'nin "
                                               'öncüsü olduğu akım nedir?',
                                          'a': 'Empresyonizm (İzlenimcilik)',
                                          'kaynak': 'MEB Görsel Sanatlar 11, s. 110',
                                          'answered': False}]}],
    'genel': [   {   'id': 'gen_1',
                     'name': 'MEB Fen Bilimleri',
                     'color': 'from-blue-600 to-indigo-600',
                     'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Yerçekimi kanununu formüle eden ve klasik mekaniğin temellerini atan '
                                               'bilim insanı kimdir?',
                                          'a': 'Isaac Newton',
                                          'kaynak': 'MEB Fizik 9, s. 128',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Güneş sistemimizde güneşe en yakın gezegen hangisidir?',
                                          'a': 'Merkür',
                                          'kaynak': 'MEB Coğrafya 9, s. 18',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': "DNA'nın çift sarmal yapısını 1953 yılında keşfeden bilim insanları "
                                               'kimlerdir?',
                                          'a': 'Watson ve Crick',
                                          'kaynak': 'MEB Biyoloji 12, s. 18',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Radyoaktivite üzerine çalışmalarıyla iki farklı alanda Nobel kazanan '
                                               'bilim insanı kimdir?',
                                          'a': 'Marie Curie',
                                          'kaynak': 'MEB Kimya 9, s. 78',
                                          'answered': False}]},
                 {   'id': 'gen_2',
                     'name': 'MEB Sosyal Bilimler',
                     'color': 'from-emerald-600 to-teal-600',
                     'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Dünyanın yedi harikasından günümüze kadar ayakta kalmayı başaran tek '
                                               'yapı hangisidir?',
                                          'a': 'Keops Piramidi (Gize)',
                                          'kaynak': 'MEB Tarih 9, s. 58',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Yaklaşık 11.000 metre derinliğiyle dünyanın en derin okyanus çukuru '
                                               'hangisidir?',
                                          'a': 'Mariana Çukuru',
                                          'kaynak': 'MEB Coğrafya 9, s. 74',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Yüzölçümü bakımından dünyanın en büyük ülkesi hangisidir?',
                                          'a': 'Rusya Federasyonu',
                                          'kaynak': 'MEB Coğrafya 9, s. 112',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Tarihte ilk yazıyı (çivi yazısını) M.Ö. 3200 civarında icat eden '
                                               'uygarlık hangisidir?',
                                          'a': 'Sümerler',
                                          'kaynak': 'MEB Tarih 9, s. 54',
                                          'answered': False}]},
                 {   'id': 'gen_3',
                     'name': 'MEB Türk Tarihi & Edebiyat',
                     'color': 'from-rose-600 to-red-600',
                     'badgeColor': 'text-rose-400 bg-rose-500/20 border-rose-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Türk edebiyatında ilk Türkçe siyasetname ve mutluluk veren bilgi '
                                               'anlamına gelen eser nedir?',
                                          'a': 'Kutadgu Bilig (Yusuf Has Hacib)',
                                          'kaynak': 'MEB Edebiyat 10, s. 36',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': "Mustafa Kemal Paşa'nın Milli Mücadele'yi başlatmak üzere Samsun'a ayak "
                                               'bastığı tarih nedir?',
                                          'a': '19 Mayıs 1919',
                                          'kaynak': 'MEB Tarih 12, s. 28',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': "Mimar Sinan'ın 'Çıraklık eserim' dediği İstanbul'daki cami hangisidir?",
                                          'a': 'Şehzade Camii',
                                          'kaynak': 'MEB Tarih 10, s. 164',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': "Türkiye'nin ilk kadın pilotu ve dünyanın ilk kadın savaş uçağı pilotu "
                                               'kimdir?',
                                          'a': 'Sabiha Gökçen',
                                          'kaynak': 'MEB Tarih 12, s. 182',
                                          'answered': False}]},
                 {   'id': 'gen_4',
                     'name': 'MEB Matematik & Mantık',
                     'color': 'from-amber-600 to-orange-600',
                     'badgeColor': 'text-amber-400 bg-amber-500/20 border-amber-500/40',
                     'questions': [   {   'points': 100,
                                          'q': 'Bir koşu yarışında ikinci durumdaki yarışmacıyı geçen bir koşucu '
                                               'kaçıncı sıraya yerleşir?',
                                          'a': 'İkinci sıraya',
                                          'kaynak': 'MEB Matematik 9, s. 42',
                                          'answered': False},
                                      {   'points': 200,
                                          'q': 'Hangi pozitif sayının karesi kendisinin 4 katına eşittir?',
                                          'a': '4',
                                          'kaynak': 'MEB Matematik 10, s. 112',
                                          'answered': False},
                                      {   'points': 300,
                                          'q': 'Bir haftada (7 gün × 24 saat) toplam kaç saat bulunmaktadır?',
                                          'a': '168 Saat',
                                          'kaynak': 'MEB Matematik 9, s. 86',
                                          'answered': False},
                                      {   'points': 400,
                                          'q': 'Bir düzine (12) ile bir destenin (10) toplamı kaçtır?',
                                          'a': '22',
                                          'kaynak': 'MEB Matematik 9, s. 32',
                                          'answered': False}]}],
    'edebiyat': [   {   'id': 'tde_1',
                        'name': 'Edebi Türler & Hikaye',
                        'color': 'from-purple-700 to-indigo-600',
                        'badgeColor': 'text-purple-400 bg-purple-500/20 border-purple-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Edebiyatımızda Batılı anlamda ilk hikaye örneği sayılan Letaif-i '
                                                  "Rivayat'ın yazarı kimdir?",
                                             'a': 'Ahmet Mithat Efendi',
                                             'kaynak': 'MEB Edebiyat 9, s. 35',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'Serim, düğüm ve çözüm bölümlerinden oluşan olay hikayeciliğinin '
                                                  '(klasik hikaye) dünya edebiyatındaki öncüsü kimdir?',
                                             'a': 'Guy de Maupassant',
                                             'kaynak': 'MEB Edebiyat 9, s. 42',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Durum (kesit) hikayeciliğinin Türk edebiyatındaki iki büyük '
                                                  'temsilcisi kimlerdir?',
                                             'a': 'Sait Faik Abasıyanık ve Memduh Şevket Esendal',
                                             'kaynak': 'MEB Edebiyat 9, s. 46',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Tarihteki ilk yazılı Türkçe edebi metinler sayılan 8. yüzyıla ait '
                                                  'anıtlar hangileridir?',
                                             'a': 'Orhun Abideleri (Göktürk Yazıtları)',
                                             'kaynak': 'MEB Edebiyat 10, s. 22',
                                             'answered': False}]},
                    {   'id': 'tde_2',
                        'name': 'Şiir Bilgisi & Nazım',
                        'color': 'from-pink-700 to-purple-600',
                        'badgeColor': 'text-pink-400 bg-pink-500/20 border-pink-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Dize sonlarında görevleri aynı olan ses, ek veya kelime '
                                                  'tekrarlarına ne ad verilir?',
                                             'a': 'Redif',
                                             'kaynak': 'MEB Edebiyat 9, s. 68',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'Dize sonlarında tek bir ses benzerliğine dayanan kafiye türüne ne '
                                                  'ad verilir?',
                                             'a': 'Yarım Kafiye',
                                             'kaynak': 'MEB Edebiyat 9, s. 70',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': "Halk edebiyatında hece ölçüsüyle yazılan ve 11'li kalıpla söylenen "
                                                  'en yaygın nazım biçimi nedir?',
                                             'a': 'Koşma',
                                             'kaynak': 'MEB Edebiyat 10, s. 75',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Divan edebiyatında aşk, şarap ve güzellik konularını işleyen, ilk '
                                                  "beyti 'matla' son beyti 'makta' olan nazım şekli nedir?",
                                             'a': 'Gazel',
                                             'kaynak': 'MEB Edebiyat 10, s. 92',
                                             'answered': False}]},
                    {   'id': 'tde_3',
                        'name': 'Söz Sanatları (Edebi Sanatlar)',
                        'color': 'from-rose-600 to-pink-600',
                        'badgeColor': 'text-rose-400 bg-rose-500/20 border-rose-500/40',
                        'questions': [   {   'points': 100,
                                             'q': 'Aralarında benzerlik ilişkisi kurularak zayıf olanın güçlü olana '
                                                  'benzetilmesi sanatına ne denir?',
                                             'a': 'Teşbih (Benzetme)',
                                             'kaynak': 'MEB Edebiyat 9, s. 84',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': 'İnsan dışındaki canlı veya cansız varlıklara insani özellikler '
                                                  'yükleme sanatına ne denir?',
                                             'a': 'Teşhis (Kişileştirme)',
                                             'kaynak': 'MEB Edebiyat 9, s. 86',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Bir duyguyu veya durumu olduğundan çok daha fazla veya az gösterme '
                                                  'sanatına ne denir?',
                                             'a': 'Mübalağa (Abartma)',
                                             'kaynak': 'MEB Edebiyat 9, s. 88',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': 'Anlamca birbirine zıt iki kavramın veya düşüncenin bir arada '
                                                  'kullanılması sanatına ne ad verilir?',
                                             'a': 'Tezat (Karşıtlık)',
                                             'kaynak': 'MEB Edebiyat 9, s. 90',
                                             'answered': False}]},
                    {   'id': 'tde_4',
                        'name': 'Dil Bilgisi & Yazım',
                        'color': 'from-indigo-600 to-blue-600',
                        'badgeColor': 'text-indigo-400 bg-indigo-500/20 border-indigo-500/40',
                        'questions': [   {   'points': 100,
                                             'q': "'Kitap - Kitabı' örneğinde görülen p harfinin b harfine dönüşmesi "
                                                  'hangi ses olayıdır?',
                                             'a': 'Ünsüz Yumuşaması (Değişimi)',
                                             'kaynak': 'MEB Edebiyat 9, s. 112',
                                             'answered': False},
                                         {   'points': 200,
                                             'q': "Cümlede yükleme sorulan 'Kim?' veya 'Ne?' sorusu öncelikle hangi "
                                                  'cümlenin öğesini buldurur?',
                                             'a': 'Özne',
                                             'kaynak': 'MEB Edebiyat 9, s. 125',
                                             'answered': False},
                                         {   'points': 300,
                                             'q': 'Bilinmeyen veya şüpheyle yaklaşılan bir bilgi/tarih belirtilirken '
                                                  'parantez içinde hangi noktalama işareti kullanılır?',
                                             'a': 'Soru İşareti (?)',
                                             'kaynak': 'MEB Edebiyat 9, s. 140',
                                             'answered': False},
                                         {   'points': 400,
                                             'q': "'Göz gezdirmek' deyiminin anlamı nedir?",
                                             'a': 'Derinlemesine incelemeden kısaca bakmak',
                                             'kaynak': 'MEB Edebiyat 9, s. 155',
                                             'answered': False}]}],
    'din': [   {   'id': 'din_1',
                   'name': 'İnanç Esasları & Tevhid',
                   'color': 'from-emerald-700 to-teal-600',
                   'badgeColor': 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40',
                   'questions': [   {   'points': 100,
                                        'q': "İslam'ın temelini oluşturan, Allah'ın birliğine ve tekliğine inanma "
                                             'esasına ne ad verilir?',
                                        'a': 'Tevhid',
                                        'kaynak': 'MEB Din Kültürü 9, s. 24',
                                        'answered': False},
                                    {   'points': 200,
                                        'q': "Allah'ın evrendeki her şeyi bir ölçü, düzen ve uyum içinde takdir edip "
                                             'planlamasına ne denir?',
                                        'a': 'Kader',
                                        'kaynak': 'MEB Din Kültürü 10, s. 38',
                                        'answered': False},
                                    {   'points': 300,
                                        'q': 'Peygamberlerin doğru, dürüst ve asla yalan söylemeyen kimseler olduğunu '
                                             'ifade eden sıfatları hangisidir?',
                                        'a': 'Sıdk',
                                        'kaynak': 'MEB Din Kültürü 9, s. 52',
                                        'answered': False},
                                    {   'points': 400,
                                        'q': 'Bir amaca ulaşmak için gerekli tüm tedbirleri aldıktan sonra sonucu '
                                             "Allah'a bırakıp güvenmeye ne denir?",
                                        'a': 'Tevekkül',
                                        'kaynak': 'MEB Din Kültürü 10, s. 42',
                                        'answered': False}]},
               {   'id': 'din_2',
                   'name': 'İbadetler & Paylaşma',
                   'color': 'from-teal-700 to-cyan-600',
                   'badgeColor': 'text-teal-400 bg-teal-500/20 border-teal-500/40',
                   'questions': [   {   'points': 100,
                                        'q': "Dinen zengin sayılan Müslümanların yılda bir kez mallarının 1/40'ını "
                                             '(%2.5) ihtiyaç sahiplerine vermesi nedir?',
                                        'a': 'Zekat',
                                        'kaynak': 'MEB Din Kültürü 9, s. 86',
                                        'answered': False},
                                    {   'points': 200,
                                        'q': 'Ramazan ayında oruca başlama vakti olan, tan yerinin ağarmasıyla imsak '
                                             'vaktine ne denir?',
                                        'a': 'İmsak',
                                        'kaynak': 'MEB Din Kültürü 9, s. 92',
                                        'answered': False},
                                    {   'points': 300,
                                        'q': 'Haccın farzlarından biri olan, Kurban Bayramı arefe günü Arafat '
                                             'bölgesinde bir süre bulunmaya ne denir?',
                                        'a': 'Vakfe',
                                        'kaynak': 'MEB Din Kültürü 9, s. 104',
                                        'answered': False},
                                    {   'points': 400,
                                        'q': 'İnsanın ölümünden sonra da sevabı devam eden cami, okul, çeşme gibi '
                                             'kalıcı hayır eserlerine ne ad verilir?',
                                        'a': 'Sadaka-i Cariye',
                                        'kaynak': 'MEB Din Kültürü 9, s. 88',
                                        'answered': False}]},
               {   'id': 'din_3',
                   'name': "Kur'an & Peygamberimiz",
                   'color': 'from-cyan-700 to-blue-600',
                   'badgeColor': 'text-cyan-400 bg-cyan-500/20 border-cyan-500/40',
                   'questions': [   {   'points': 100,
                                        'q': "Kur'an-ı Kerim'in Hz. Muhammed'e indirilmeye başlandığı 610 yılındaki "
                                             'mübarek gece hangisidir?',
                                        'a': 'Kadir Gecesi',
                                        'kaynak': 'MEB Din Kültürü 9, s. 44',
                                        'answered': False},
                                    {   'points': 200,
                                        'q': "Hz. Peygamber'e Hira Mağarası'nda vahyedilen Alak suresinin ilk emri "
                                             'nedir?',
                                        'a': 'Oku! (İkra)',
                                        'kaynak': 'MEB Din Kültürü 9, s. 42',
                                        'answered': False},
                                    {   'points': 300,
                                        'q': "Hz. Muhammed'in (s.a.v.) 632 yılında hac sırasında evrensel insan "
                                             'hakları ilkelerini ilan ettiği hitabesi nedir?',
                                        'a': 'Veda Hutbesi',
                                        'kaynak': 'MEB Din Kültürü 10, s. 95',
                                        'answered': False},
                                    {   'points': 400,
                                        'q': "Müslümanların 622 yılında Mekke'den Medine'ye göç etmesine ve Hicri "
                                             'takvimin başlangıcı sayılan olaya ne denir?',
                                        'a': 'Hicret',
                                        'kaynak': 'MEB Din Kültürü 9, s. 60',
                                        'answered': False}]},
               {   'id': 'din_4',
                   'name': 'Ahlak & Tasavvuf',
                   'color': 'from-blue-700 to-indigo-600',
                   'badgeColor': 'text-blue-400 bg-blue-500/20 border-blue-500/40',
                   'questions': [   {   'points': 100,
                                        'q': 'Yapılan ibadet ve iyiliklerin yalnızca Allah rızası gözetilerek, '
                                             'gösterişten uzak yapılmasına ne ad verilir?',
                                        'a': 'İhlas',
                                        'kaynak': 'MEB Din Kültürü 10, s. 68',
                                        'answered': False},
                                    {   'points': 200,
                                        'q': 'Bir kimsenin arkasından hoşlanmayacağı doğru kusurlarını konuşarak onu '
                                             'çekiştirmeye ne ad verilir?',
                                        'a': 'Gıybet',
                                        'kaynak': 'MEB Din Kültürü 10, s. 74',
                                        'answered': False},
                                    {   'points': 300,
                                        'q': "'Yaratılanı severiz, Yaratandan ötürü' sözüyle sevgi ve hoşgörüyü "
                                             'anlatan büyük Türk mutasavvıfı kimdir?',
                                        'a': 'Yunus Emre',
                                        'kaynak': 'MEB Din Kültürü 12, s. 84',
                                        'answered': False},
                                    {   'points': 400,
                                        'q': 'İsrafil (a.s.) tarafından Sûr borusuna ikinci kez üflenmesiyle '
                                             'insanların yeniden diriltilmesine ne denir?',
                                        'a': "Ba's (Diriliş)",
                                        'kaynak': 'MEB Din Kültürü 11, s. 22',
                                        'answered': False}]}]}

VARSAYILAN_SORULAR["gorsel_sanatlar"] = VARSAYILAN_SORULAR["sanat"]


def _webui_anahtari() -> str:
    try:
        if API_KEYS_YOLU.exists():
            data = json.loads(API_KEYS_YOLU.read_text(encoding="utf-8"))
            return data.get("webui_key", "")
    except Exception as e:
        log.warning("api_keys.json okunamadı: %s", e)
    return ""


def normalize_ders_adi(s: str) -> str:
    if not s:
        return ""
    return turkce.kapsam_anahtari(s)


def hazir_sorulari_getir(ders_adi: str) -> list[dict[str, Any]]:
    """Ders adına en uygun hazır müfredat soru setini anında döner."""
    ders_temiz = normalize_ders_adi(ders_adi)

    # 1. Kapsam eşleme dene
    hedef_kapsam = KAPSAM_ESLEME.get(ders_temiz)
    for k, v in ([] if hedef_kapsam else KAPSAM_ESLEME.items()):
        k_norm = normalize_ders_adi(k)
        if k_norm in ders_temiz or ders_temiz in k_norm:
            hedef_kapsam = v
            break

    if hedef_kapsam and hedef_kapsam in VARSAYILAN_SORULAR:
        return json.loads(json.dumps(VARSAYILAN_SORULAR[hedef_kapsam]))

    # 2. Doğrudan anahtarlarda ara
    for k in VARSAYILAN_SORULAR:
        k_norm = normalize_ders_adi(k)
        if k_norm in ders_temiz or ders_temiz in k_norm:
            return json.loads(json.dumps(VARSAYILAN_SORULAR[k]))

    # Fallback: Biyoloji
    return json.loads(json.dumps(VARSAYILAN_SORULAR["biyoloji"]))


async def rag_icerik_ara(ders_adi: str, sinif_no: int = 9, arama_sorgusu: str = "") -> list[dict[str, Any]]:
    """Farabi Brain POST /api/webui/ara üzerinden ders kitabı parçalarını çeker."""
    kapsam = KAPSAM_ESLEME.get(turkce.kapsam_anahtari(ders_adi), "genel")
    webui_key = _webui_anahtari()
    if not webui_key:
        log.warning("WebUI key bulunamadı.")
        return []

    if not arama_sorgusu:
        arama_sorgusu = f"{sinif_no}. sınıf {ders_adi} temel kavramlar konular"

    payload = {
        "kapsam": kapsam,
        "soru": arama_sorgusu,
        "sinif": sinif_no,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{FARABI_API_URL}/api/webui/ara",
                json=payload,
                headers={"X-Farabi-WebUI-Key": webui_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("parcalar", [])
    except Exception as e:
        log.warning("RAG araması başarısız: %s", e)
    return []


async def ollama_soru_uret(
    ders_adi: str,
    sinif_no: int = 9,
    konu: str = "",
    rag_parcalari: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """Yerel Ollama (qwen3.8:27b) ile ders kitabı kaynaklı 4x4 Jeopardy seti üretir."""
    rag_metinleri = ""
    kaynak_etiketleri = []
    if rag_parcalari:
        for p in rag_parcalari[:5]:
            kaynak_etiketleri.append(p.get("kaynak", f"MEB {ders_adi} {sinif_no}"))
            rag_metinleri += f"\n--- Kaynak: {p.get('kaynak')} ---\n{p.get('metin', '')[:400]}\n"

    varsayilan_kaynak = f"MEB {turkce.tr_baslik(ders_adi)} {sinif_no}, s. 45"
    ana_kaynak = kaynak_etiketleri[0] if kaynak_etiketleri else varsayilan_kaynak
    if not str(ana_kaynak).startswith("MEB "):
        ana_kaynak = f"MEB {ana_kaynak}"

    dil_notu = ""
    if KAPSAM_ESLEME.get(turkce.kapsam_anahtari(ders_adi)) == "almanca":
        dil_notu = (
            "BU DERS ALMANCA DİL DERSİDİR: sorular Almanca kelime, dilbilgisi (Artikel, fiil çekimi, "
            "cümle yapısı) ve günlük konuşma üzerine olsun; örnek cümleler ve cevaplar ALMANCA olsun "
            "(açıklayıcı soru kökü Türkçe olabilir). İngilizce soru ÜRETME. "
        )
    sistem_prompt = (
        dil_notu +
        "Sen MEB lise müfredatına tam hakim bir Türk lise öğretmenisin. "
        "Akıllı tahtada oynanacak Sınıf Arenası Jeopardy yarışması için 4 KATEGORİ ve "
        "her kategoride 4 FARKLI ZORLUKTA (100, 200, 300, 400 puanlık) soru hazırla (toplam 16 soru). "
        "ÖNEMLİ KURAL: Tüm soru ve cevaplar İSTİSNASIZ sadece MEB Ders Kitaplarından türetilmelidir. "
        "Dış kaynak, internet veya genel kültür kaynağı KULLANMA. "
        "YASAK: KESİNLİKLE karekod, QR kod, barkod, simülasyon aracı, web sitesi, link, video, sayfa numarası, "
        "etkinlik yönergesi veya 'metne göre', 'şekildeki' gibi öğrencinin tahtada görmediği unsurlar hakkında soru ÜRETME. "
        "Soru ve cevaplar doğrudan bilimsel/akademik konu kavramlarını ölçsün. "
        "Her sorunun 'kaynak' alanına mutlaka 'MEB <Ders> <Sınıf>, s. <Sayfa>' formatında resmi MEB kitap referansını yaz. "
        "Soru ve cevaplar kısa, net, tek cümle olsun. "
        "SADECE GEÇERLİ JSON DIZISI (Array) DÖNDÜR, hiçbir ek metin veya selamlama yazma."
    )

    kullanici_prompt = f"""Ders: {ders_adi} ({sinif_no}. Sınıf)
Konu/Odak: {konu if konu else 'Müfredat temel kavramları'}

Kaynak Kitap Parçaları:
{rag_metinleri if rag_metinleri else f'MEB {turkce.tr_baslik(ders_adi)} {sinif_no} Ders Kitabı'}

JSON FORMATI:
[
  {{
    "id": "kat_1",
    "name": "Kategori Adı",
    "color": "from-emerald-600 to-teal-600",
    "badgeColor": "text-emerald-400 bg-emerald-500/20 border-emerald-500/40",
    "questions": [
      {{"points": 100, "q": "Kısa soru?", "a": "Kısa cevap.", "kaynak": "{ana_kaynak}"}},
      {{"points": 200, "q": "Kısa soru?", "a": "Kısa cevap.", "kaynak": "{ana_kaynak}"}},
      {{"points": 300, "q": "Kısa soru?", "a": "Kısa cevap.", "kaynak": "{ana_kaynak}"}},
      {{"points": 400, "q": "Kısa soru?", "a": "Kısa cevap.", "kaynak": "{ana_kaynak}"}}
    ]
  }}
]
"""

    renk_paleti = [
        {"color": "from-blue-600 to-indigo-600", "badgeColor": "text-blue-400 bg-blue-500/20 border-blue-500/40"},
        {"color": "from-emerald-600 to-teal-600", "badgeColor": "text-emerald-400 bg-emerald-500/20 border-emerald-500/40"},
        {"color": "from-amber-600 to-orange-600", "badgeColor": "text-amber-400 bg-amber-500/20 border-amber-500/40"},
        {"color": "from-purple-600 to-pink-600", "badgeColor": "text-purple-400 bg-purple-500/20 border-purple-500/40"},
    ]

    payload = {
        "model": "qwen3.8:27b",
        "messages": [
            {"role": "system", "content": sistem_prompt},
            {"role": "user", "content": kullanici_prompt},
        ],
        "stream": False,
        "think": False,  # CLAUDE.md Kuralı: Ollama çağrısında düşünme KAPALI
    }

    try:
        async with httpx.AsyncClient(timeout=75.0) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            if resp.status_code == 200:
                veri = resp.json()
                icerik = veri.get("message", {}).get("content", "")
                # Markdown bloklarını temizle
                temiz = re.sub(r"^```json\s*", "", icerik, flags=re.MULTILINE)
                temiz = re.sub(r"^```\s*", "", temiz, flags=re.MULTILINE).strip()

                parsed = json.loads(temiz)
                if isinstance(parsed, list) and len(parsed) >= 4:
                    # Karekod veya geçersiz içerik denetimi
                    yasak_regex = re.compile(r"karekod|qr\s*kod|barkod", re.IGNORECASE)
                    for cat in parsed[:4]:
                        for q in cat.get("questions", []):
                            if yasak_regex.search(q.get("q", "")) or yasak_regex.search(q.get("a", "")):
                                log.warning("Ollama çıktısında karekod/QR tespit edildi, set reddedildi: %s", q.get("q"))
                                return None

                    # Renk ve answered alanlarını garanti et
                    for idx, cat in enumerate(parsed[:4]):
                        cat["id"] = f"ai_kat_{idx+1}"
                        cat["color"] = renk_paleti[idx % 4]["color"]
                        cat["badgeColor"] = renk_paleti[idx % 4]["badgeColor"]
                        for q in cat.get("questions", []):
                            q["answered"] = False
                            if "kaynak" not in q or not q["kaynak"] or not str(q["kaynak"]).startswith("MEB "):
                                q["kaynak"] = ana_kaynak
                    return parsed[:4]
    except Exception as e:
        log.warning("Ollama soru üretimi hatası: %s", e)

    return None
