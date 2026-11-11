export type PdfFont = "helv" | "tiro" | "cour";
export type EditorTool = "pointer" | "text" | "image" | "ink" | "highlight" | "rect" | "line";

export interface ElementBase {
  id: string;
  page: number;
  kind: PdfElement["kind"];
}

export interface TextElement extends ElementBase {
  kind: "text";
  x: number;
  y: number;
  w: number;
  text: string;
  font: PdfFont;
  bold: boolean;
  size: number;
  color: string;
}

export interface ImageElement extends ElementBase {
  kind: "image";
  x: number;
  y: number;
  w: number;
  h: number;
  path: string;
}

export interface InkElement extends ElementBase {
  kind: "ink";
  points: [number, number][];
  color: string;
  width: number;
}

export interface HighlightElement extends ElementBase {
  kind: "highlight";
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
}

export interface RectElement extends ElementBase {
  kind: "rect";
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  width: number;
}

export interface LineElement extends ElementBase {
  kind: "line";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color: string;
  width: number;
}

export type PdfElement = TextElement | ImageElement | InkElement | HighlightElement | RectElement | LineElement;

export function cloneElements(elements: PdfElement[]): PdfElement[] {
  return elements.map((element) => element.kind === "ink"
    ? { ...element, points: element.points.map(([x, y]) => [x, y] as [number, number]) }
    : { ...element });
}

export function fontFamily(font: PdfFont): string {
  return font === "tiro" ? '"Times New Roman", serif' : font === "cour" ? '"Courier New", monospace' : "Helvetica, Arial, sans-serif";
}

export function elementLabel(element: PdfElement): string {
  if (element.kind === "text") return element.text.replace(/\s+/g, " ").trim().slice(0, 28) || "Texto";
  if (element.kind === "image") return element.path.split(/[\\/]/).pop() || "Imagen";
  if (element.kind === "ink") return "Dibujo";
  if (element.kind === "highlight") return "Resaltado";
  if (element.kind === "rect") return "Rectángulo";
  return "Línea";
}
