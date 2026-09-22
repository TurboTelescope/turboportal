import Tooltip from "@mui/material/Tooltip";

interface KnownObject {
  catalog: string;
  ident: string;
  kind?: string;
  vclass?: string;
  vtype?: string;
  period?: number;
  amplitude?: number;
  sep_arcsec?: number;
  url?: string;
}

interface SourceKnownObjectProps {
  known_object: KnownObject;
}

// Catalogue values carry more digits than fit on one line.
const round = (value: number) => Number(value.toPrecision(4));

const SourceKnownObject = ({ known_object }: SourceKnownObjectProps) => {
  const { catalog, ident, vtype, period, amplitude, sep_arcsec, url } =
    known_object;

  const details = [
    vtype,
    period != null && `P = ${round(period)} d`,
    amplitude != null && `A = ${round(amplitude)} mag`,
  ].filter(Boolean);

  const tooltip =
    sep_arcsec != null
      ? `${catalog}, ${round(sep_arcsec)} arcsec away`
      : catalog;

  return (
    <>
      <b>Known object: &nbsp;</b>
      <Tooltip title={tooltip}>
        {url ? (
          <a href={url} target="_blank" rel="noreferrer">
            {ident}
          </a>
        ) : (
          <span>{ident}</span>
        )}
      </Tooltip>
      {details.length > 0 && <span>{` · ${details.join(" · ")}`}</span>}
    </>
  );
};

export default SourceKnownObject;
