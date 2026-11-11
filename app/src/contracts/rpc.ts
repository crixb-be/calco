export type PageRotation = 0 | 90 | 180 | 270;

export interface PageRef {
  sourceIndex: number;
  pageIndex: number;
  rotation?: PageRotation;
}

export interface PageOperationPlan {
  sourcePath: string;
  pageOrder: number[];
  rotations: Record<number, number>;
  deletedPages: number[];
}

export interface PdfPageMetadata {
  index: number;
  width: number;
  height: number;
  rotation: number;
}

export interface PdfPagesMetadataParams {
  pdfPath: string;
  password?: string;
}

export type ThumbnailTier = "S" | "M" | "L" | "XL";

export interface PdfPagesMetadataResult {
  fileHash: string;
  pageCount: number;
  pages: PdfPageMetadata[];
}

export interface PageThumbnailsParams {
  pdfPath: string;
  start: number;
  count: number;
  maxWidth?: number;
  tier?: ThumbnailTier;
  format?: "webp" | "png";
}

export interface PageThumbnail {
  index: number;
  thumbUrl: string;
  width: number;
  height: number;
}

export interface PageThumbnailsResult {
  pages: PageThumbnail[];
}

export interface OrganizerThumbnail {
  page_index: number;
  page_number: number;
  rotation: PageRotation;
  thumbnail: string;
  width: number;
  height: number;
}

export interface PdfThumbnailsResult {
  pages: OrganizerThumbnail[];
  dpi: number;
}

export interface HistoryRecord {
  id: string;
  type: string;
  source_name: string;
  target_path: string;
  timestamp: string;
  status: "success" | "error" | "cancelled" | string;
  duration_ms: number;
}

export interface RenderPageParams {
  pdfPath: string;
  index: number;
  maxWidth?: number;
  tier?: "modal";
}

export interface RenderPageResult {
  index: number;
  imageUrl: string;
  width: number;
  height: number;
}

export interface ReadTextFileParams {
  path: string;
  maxBytes?: number;
}

export interface ReadTextFileResult {
  content: string;
  size: number;
}

export interface ExportFileParams {
  sourcePath: string;
  targetPath: string;
}

export interface ExportFileResult {
  path: string;
}

export interface RpcContracts {
  get_pdf_pages_metadata: {
    params: PdfPagesMetadataParams;
    result: PdfPagesMetadataResult;
  };
  get_page_thumbnails: {
    params: PageThumbnailsParams;
    result: PageThumbnailsResult;
  };
  get_pdf_thumbnails: {
    params: { source_pdf: string };
    result: PdfThumbnailsResult;
  };
  get_history: {
    params: Record<string, never>;
    result: { records: HistoryRecord[] };
  };
  clear_history: {
    params: Record<string, never>;
    result: { records: HistoryRecord[] };
  };
  render_page: {
    params: RenderPageParams;
    result: RenderPageResult;
  };
  read_text_file: {
    params: ReadTextFileParams;
    result: ReadTextFileResult;
  };
  export_file: {
    params: ExportFileParams;
    result: ExportFileResult;
  };
}

export type RpcMethod = keyof RpcContracts;
export type RpcParams<M extends RpcMethod> = RpcContracts[M]["params"];
export type RpcResult<M extends RpcMethod> = RpcContracts[M]["result"];
