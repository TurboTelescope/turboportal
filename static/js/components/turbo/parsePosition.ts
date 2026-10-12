export interface SkyPosition {
  ra: number;
  dec: number;
}

const NUMBER = /[+-]?\d+(?:\.\d+)?/g;

// Degrees ("239.8757 25.9203") or sexagesimal with RA in hours
// ("15:59:30.2 +25:55:13", "15h59m30.2s +25d55m13s"); null if neither.
export const parsePosition = (text: string): SkyPosition | null => {
  const tokens = text.replace(/[,;]/g, " ").match(NUMBER);
  if (!tokens) return null;
  let ra: number;
  let dec: number;
  if (tokens.length === 2) {
    ra = Number(tokens[0]);
    dec = Number(tokens[1]);
  } else if (tokens.length === 6) {
    const [h, m, s, d, dm, ds] = tokens as [
      string,
      string,
      string,
      string,
      string,
      string,
    ];
    if (
      Number(m) >= 60 ||
      Number(s) >= 60 ||
      Number(dm) >= 60 ||
      Number(ds) >= 60
    )
      return null;
    ra = 15 * (Number(h) + Number(m) / 60 + Number(s) / 3600);
    const sign = d.startsWith("-") ? -1 : 1;
    dec = sign * (Math.abs(Number(d)) + Number(dm) / 60 + Number(ds) / 3600);
  } else {
    return null;
  }
  if (!(ra >= 0 && ra < 360 && dec >= -90 && dec <= 90)) return null;
  return { ra, dec };
};
