// Centralized date utilities

// Format a date-like value to 'Month Day, Year'.
// - For ISO date-only strings (YYYY-MM-DD) we avoid timezone conversion to prevent off-by-one issues.
// - For full timestamps, we use native Date parsing and locale formatting.
export function formatDateSafe(value: unknown, locale: string = 'en-US'): string {
  if (value === null || value === undefined || value === '') return '-';

  if (typeof value === 'string') {
    const m = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) {
      const [, y, mm, dd] = m;
      const monthNames = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
      ];
      const monthIdx = Math.max(0, Math.min(11, parseInt(mm, 10) - 1));
      const dayNum = parseInt(dd, 10);
      return `${monthNames[monthIdx]} ${dayNum}, ${y}`;
    }
  }

  let d: Date;
  if (typeof value === 'string' || typeof value === 'number') {
    d = new Date(value);
  } else if (value instanceof Date) {
    d = value;
  } else {
    return '-';
  }
  if (typeof d.getTime !== 'function' || isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString(locale, { year: 'numeric', month: 'long', day: 'numeric' });
}

// Format a timestamp string as local date-time with timezone abbreviation.
export function formatLocalDateTimeWithTZ(value: string | null | undefined, locale?: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (isNaN(date.getTime())) return value;
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false, timeZoneName: 'short'
  };
  return new Intl.DateTimeFormat(locale, options).format(date);
}
