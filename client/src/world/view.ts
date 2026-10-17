export type Point = { x: number; y: number };
export type Size = { width: number; height: number };

export function toCanvas(point: Point, scroll: Point, view: Size, zoom: number): Point {
  return {
    x: (point.x - scroll.x - view.width / 2) * zoom + view.width / 2,
    y: (point.y - scroll.y - view.height / 2) * zoom + view.height / 2,
  };
}

export type Viewport = { innerWidth: number; innerHeight: number; devicePixelRatio: number };
