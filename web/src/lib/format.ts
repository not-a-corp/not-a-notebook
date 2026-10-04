// How numbers, sizes and times read in the interface's chrome. UI copy is
// English (decision 14), so these use English separators: 1,286 rows.

const integer = new Intl.NumberFormat("en-US");

export function formatCount(value: number): string {
  return integer.format(value);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${String(bytes)} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${String(Math.round(bytes / 1024))} KB`;
  }
  const megabytes = bytes / (1024 * 1024);
  return `${megabytes.toFixed(1)} MB`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${String(Math.round(ms))} ms`;
  }
  const seconds = ms / 1000;
  return `${seconds.toFixed(1)} s`;
}

export function formatClock(iso: string): string {
  const date = new Date(iso);
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function plural(count: number, one: string, many: string): string {
  if (count === 1) {
    return `${formatCount(count)} ${one}`;
  }
  return `${formatCount(count)} ${many}`;
}
