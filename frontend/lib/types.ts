// Mirrors traceq/backend/traceq/models.py field-for-field (FastAPI/pydantic
// serializes as snake_case JSON).

export type Verdict = "VERIFIED_ORIGIN" | "DERIVED" | "NO_RECORD";

export interface PipelineMatch {
  name: string;
  confidence: "high" | "medium" | "low" | string;
  basis: string[];
}

export interface ForensicStats {
  mean_residual_noise: number | null;
  chromatic_aberration_px: number | null;
  note: string;
}

export interface GPSInfo {
  latitude: number | null;
  longitude: number | null;
}

export interface ExifData {
  present: boolean;
  make: string | null;
  model: string | null;
  software: string | null;
  datetime_original: string | null;
  exposure_time: string | number | null;
  fnumber: number | null;
  iso: number | null;
  has_gps_ifd: boolean;
  has_thumbnail_ifd: boolean;
  subsec_time: string | null;
  gps: GPSInfo | null;
  raw: Record<string, unknown>;
}

export interface C2PAData {
  present: boolean;
  valid: boolean | null;
  software_agent: string | null;
  digital_source_type: string | null;
  generator: string | null;
  timestamp: string | null;
  claim_generator: string | null;
  assertions: string[];
}

export interface ICCData {
  present: boolean;
  description: string | null;
  copyright: string | null;
}

export interface EncoderFingerprint {
  quant_table_luma: number[] | null;
  quant_table_chroma: number[] | null;
  quant_tables_identical: boolean;
  is_progressive: boolean;
  chroma_subsampling: string | null;
}

export interface FileRecord {
  sha256: string;
  declared_format: string;
  actual_format: string;
  format_mismatch: boolean;
  file_size: number;
  width: number | null;
  height: number | null;
  c2pa: C2PAData;
  exif: ExifData;
  icc: ICCData;
  encoder: EncoderFingerprint;
  trailing_byte_count: number;
  min_flat_region_std: number | null;
  pipeline_matches: PipelineMatch[];
  phash: string | null;
  dhash: string | null;
  ahash: string | null;
  whash: string | null;
  orb_descriptor_count: number | null;
  stats: ForensicStats;
}

export interface DerivationInfo {
  parent_sha256: string;
  parent_filename: string | null;
  transformations_detected: string[];
  hash_distance: number;
  hash_type: string;
}

export interface TraceScore {
  value: number;
  max_value: number;
  label: string;
  breakdown: Record<string, number>;
}

export interface Observations {
  pipeline_inference: PipelineMatch[];
  transformations_detected: string[];
  format_mismatch: boolean;
  embedded_credentials: Record<string, unknown>;
}

export interface AnalysisResult {
  file_id: string;
  filename: string;
  verdict: Verdict;
  verdict_statement: string;
  trace_score: TraceScore;
  record: FileRecord;
  derivation: DerivationInfo | null;
  observations: Observations;
}

export interface GraphNode {
  id: string;
  filename: string;
  verdict: Verdict;
  badges: string[];
  trace_score: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string;
}

export interface SessionGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
