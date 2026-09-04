import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import Button from "../Button";
import {
  useDeleteFPCutoutsMutation,
  useFpCutoutsQuery,
} from "../../ducks/fp_cutouts";
import {
  useFetchSourcePhotometryQuery,
  type PhotometryPoint,
} from "../../ducks/photometry";

const FP_ORIGIN = "TURBO_forced";
const CELL = "5.5rem";

interface SourceFPCutoutsProps {
  objId: string;
  isReadOnly?: boolean;
}

// Photometry fields beyond id/obj_id come from an index signature, so they are
// read with bracket access.
const fmtMag = (p: PhotometryPoint | undefined) => {
  if (p?.["mag"] != null) return Number(p["mag"]).toFixed(2);
  if (p?.["limiting_mag"] != null)
    return `>${Number(p["limiting_mag"]).toFixed(2)}`;
  return "";
};

/**
 * DIF cutouts behind a source's forced-photometry points, so an upper limit
 * can be eyeballed rather than trusted. Requesting them is an option on the
 * TURBO forced-photometry follow-up form; this displays and clears them.
 */
const SourceFPCutouts = ({
  objId,
  isReadOnly = false,
}: SourceFPCutoutsProps) => {
  const { data: cutouts, isLoading } = useFpCutoutsQuery(objId);
  const { data: photometry } = useFetchSourcePhotometryQuery({ id: objId });
  const [deleteCutouts, { isLoading: isDeleting }] =
    useDeleteFPCutoutsMutation();

  // The endpoint returns only the photometry id each cutout hangs off, so the
  // epoch labels come from the photometry already loaded for this source.
  const byId = new Map<number, PhotometryPoint>(
    (photometry ?? [])
      .filter((p) => p["origin"] === FP_ORIGIN)
      .map((p) => [p.id, p]),
  );

  if (isLoading) {
    return <CircularProgress size={24} />;
  }
  if (!cutouts?.length) {
    return (
      <Typography variant="body2">
        No forced-photometry cutouts. Request them from the Forced Photometry
        form using the &quot;DIF cutouts&quot; option.
      </Typography>
    );
  }

  const sorted = [...cutouts].sort(
    (a, b) =>
      (byId.get(a.photometry_id ?? -1)?.["mjd"] ?? 0) -
      (byId.get(b.photometry_id ?? -1)?.["mjd"] ?? 0),
  );

  return (
    <Box sx={{ width: "100%" }}>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: `repeat(auto-fill, minmax(${CELL}, 1fr))`,
          gap: "0.75rem 0.5rem",
          marginBottom: "0.75rem",
        }}
      >
        {sorted.map((c) => {
          const p = byId.get(c.photometry_id ?? -1);
          const mjd = p?.["mjd"] != null ? Number(p["mjd"]).toFixed(3) : "?";
          const band = (p?.["filter"] ?? "").replace(/^sdss/, "");
          return (
            <Box key={c.id} sx={{ textAlign: "center", minWidth: 0 }}>
              <Tooltip
                title={`MJD ${mjd} · ${band} ${fmtMag(p)}`}
                placement="top"
              >
                {/* Fixed-size frame so a cutout that fails to load leaves a
                    placeholder rather than collapsing the grid; alt is empty
                    for the same reason -- the labels below carry the text. */}
                <Box
                  sx={{
                    width: CELL,
                    height: CELL,
                    margin: "0 auto",
                    border: "1px solid",
                    borderColor: "divider",
                    backgroundColor: "action.hover",
                  }}
                >
                  <img
                    src={c.public_url ?? ""}
                    alt=""
                    loading="lazy"
                    style={{
                      width: "100%",
                      height: "100%",
                      display: "block",
                      imageRendering: "pixelated",
                    }}
                  />
                </Box>
              </Tooltip>
              <Typography
                variant="caption"
                component="div"
                sx={{ lineHeight: 1.3, fontVariantNumeric: "tabular-nums" }}
              >
                {band} {fmtMag(p)}
              </Typography>
              <Typography
                variant="caption"
                component="div"
                sx={{
                  lineHeight: 1.3,
                  opacity: 0.7,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {mjd}
              </Typography>
            </Box>
          );
        })}
      </Box>
      {!isReadOnly && (
        <Button
          secondary
          onClick={() => deleteCutouts(objId)}
          disabled={isDeleting}
          data-testid="delete-fp-cutouts-button"
        >
          Delete all cutouts
        </Button>
      )}
    </Box>
  );
};

export default SourceFPCutouts;
