/** URL `asOf=YYYY-MM-DD` validation and inclusive end-of-day UTC for Prisma filters. */

export const AS_OF_ISO = /^\d{4}-\d{2}-\d{2}$/;

export function asOfEndUtc(iso: string): Date {
  return new Date(`${iso}T23:59:59.999Z`);
}
