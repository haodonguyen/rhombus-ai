const BYTE_UNITS = ["KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${BYTE_UNITS[unit]}`;
}

export function formatNumber(value: number | null): string {
  return value === null ? "—" : value.toLocaleString("en-US");
}

/** "TRANSFORMING" -> "Transforming" */
export function formatStage(stage: string): string {
  return stage.charAt(0) + stage.slice(1).toLowerCase().replaceAll("_", " ");
}
