// Vista previa 9:16 aproximada de lo que hace clipero/frame.py (layout_graph y _scene_canvas).
import type { Rect } from './api';

// = clipero/frame.py:21 (W, H) y :133-135 (FACE_Y, STRIP_Y, STRIP_H)
export const W = 1080;
export const H = 1920;
export const FACE_Y = 80;
export const STRIP_Y = 690;
export const STRIP_H = 608;

export type Modo = 'plano' | 'recuadro' | 'ancho' | 'cara';
export type Rects = { facecam?: Rect; juego?: Rect };

const par = (v: number) => Math.round(v / 2) * 2;   // = frame._even

/** Dibuja en `ctx` (canvas de W*k × H*k) la composición de `modo`. `entrada` = [iw, ih] del layout. */
export function dibujar(
  ctx: CanvasRenderingContext2D, img: HTMLImageElement | null, entrada: [number, number],
  modo: Modo, r: Rects, k = 0.25,
) {
  ctx.save();
  ctx.filter = 'none';
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, W * k, H * k);
  if (!img || !img.naturalWidth) {
    ctx.fillStyle = '#888';
    ctx.font = `${14}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('Sin imagen', (W * k) / 2, (H * k) / 2);
    ctx.restore();
    return;
  }
  const nw = img.naturalWidth, nh = img.naturalHeight;
  const sx = nw / entrada[0], sy = nh / entrada[1];
  const trozo = (c: Rect, dx: number, dy: number, dw: number, dh: number) =>
    ctx.drawImage(img, c.x * sx, c.y * sy, c.w * sx, c.h * sy, dx * k, dy * k, dw * k, dh * k);
  const valido = (c?: Rect): c is Rect => !!c && c.w > 0 && c.h > 0;
  const fondo = () => {
    const s = Math.max(W / nw, H / nh);
    ctx.save();
    ctx.filter = `blur(${Math.max(1, 24 * k)}px)`;
    ctx.drawImage(img, ((W - nw * s) / 2) * k, ((H - nh * s) / 2) * k, nw * s * k, nh * s * k);
    ctx.restore();
  };

  if (modo === 'plano') {
    if (valido(r.facecam)) trozo(r.facecam, 0, 0, W, 810);
    if (valido(r.juego)) trozo(r.juego, 0, 810, W, 810);
  } else if (modo === 'cara') {
    const cw = (nh * 9) / 16;   // recorte 9:16 centrado (el render real sigue la cara)
    ctx.drawImage(img, (nw - cw) / 2, 0, cw, nh, 0, 0, W * k, H * k);
  } else if (modo === 'ancho') {
    fondo();
    ctx.drawImage(img, 0, 0, nw, nh, 0, STRIP_Y * k, W * k, STRIP_H * k);
  } else {
    fondo();
    if (valido(r.juego)) trozo(r.juego, 0, STRIP_Y, W, STRIP_H);
    if (valido(r.facecam)) trozo(r.facecam, 0, FACE_Y, W, par((W * r.facecam.h) / r.facecam.w));
  }
  ctx.restore();
}
