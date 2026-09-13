import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";

import Button from "../Button";
import type { PhotometryPoint } from "../../ducks/photometry";
import type { PhotometryCutout } from "../../ducks/photometry_cutouts";

const CUTOUT_SIZE = "11rem";

interface PhotometryCutoutPopoverProps {
  anchor: { top: number; left: number } | null;
  point: PhotometryPoint | undefined;
  cutout: PhotometryCutout | undefined;
  unavailable: boolean;
  onRequest: () => void;
  onClose: () => void;
}

const describePoint = (point: PhotometryPoint | undefined) => {
  if (!point) {
    return "";
  }
  const band = String(point["filter"] ?? "").replace(/^sdss/, "");
  const mjd = Number(point["mjd"]).toFixed(4);
  if (point["mag"] != null) {
    return `${band} ${Number(point["mag"]).toFixed(2)} · MJD ${mjd}`;
  }
  if (point["limiting_mag"] != null) {
    return `${band} >${Number(point["limiting_mag"]).toFixed(2)} · MJD ${mjd}`;
  }
  return `${band} · MJD ${mjd}`;
};

const CutoutBody = ({
  cutout,
  unavailable,
  onRequest,
}: Pick<
  PhotometryCutoutPopoverProps,
  "cutout" | "unavailable" | "onRequest"
>) => {
  if (unavailable) {
    return (
      <Typography variant="body2">
        No archived frame is recorded for this point.
      </Typography>
    );
  }
  if (!cutout) {
    return (
      <Button secondary size="small" onClick={onRequest}>
        Request cutout
      </Button>
    );
  }
  if (cutout.status === "ready") {
    return (
      <img
        src={cutout.public_url ?? ""}
        alt="Difference-image cutout"
        style={{
          width: CUTOUT_SIZE,
          height: CUTOUT_SIZE,
          display: "block",
          imageRendering: "pixelated",
        }}
      />
    );
  }
  if (cutout.status === "failed") {
    return (
      <>
        <Typography variant="body2" color="error">
          {cutout.error || "The cutout could not be made."}
        </Typography>
        <Button secondary size="small" onClick={onRequest}>
          Retry
        </Button>
      </>
    );
  }
  return (
    <>
      <Box sx={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <CircularProgress size={18} />
        <Typography variant="body2">Rendering cutout…</Typography>
      </Box>
      {cutout.stale && (
        <Button secondary size="small" onClick={onRequest}>
          Request again
        </Button>
      )}
    </>
  );
};

const PhotometryCutoutPopover = ({
  anchor,
  point,
  cutout,
  unavailable,
  onRequest,
  onClose,
}: PhotometryCutoutPopoverProps) => (
  <Popover
    open={anchor !== null}
    onClose={onClose}
    anchorReference="anchorPosition"
    anchorPosition={anchor ?? { top: 0, left: 0 }}
    transformOrigin={{ vertical: "bottom", horizontal: "center" }}
  >
    <Box
      sx={{
        padding: "0.75rem",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "0.5rem",
        maxWidth: "16rem",
      }}
    >
      <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>
        {describePoint(point)}
      </Typography>
      <CutoutBody
        cutout={cutout}
        unavailable={unavailable}
        onRequest={onRequest}
      />
    </Box>
  </Popover>
);

export default PhotometryCutoutPopover;
