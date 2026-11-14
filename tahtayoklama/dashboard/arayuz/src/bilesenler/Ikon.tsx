import React from 'react';

interface IkonProps {
  ad: string;
  className?: string;
}

// SVG sprite'tan satır içi çağrı; harici ikon kütüphanesi yok (Global Constraint).
// Sprite kaynağı templates/_ikon_sprite.html (#ik-<ad>).
export const Ikon: React.FC<IkonProps> = ({ ad, className = 'h-5 w-5' }) => (
  <svg className={className} aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round">
    <use href={`#ik-${ad}`} />
  </svg>
);
