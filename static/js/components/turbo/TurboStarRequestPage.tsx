import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import { showNotification } from "baselayer/components/Notifications";

import Button from "../Button";
import StyledDataGrid from "../StyledDataGrid";
import GroupShareSelect from "../group/GroupShareSelect";
import { useGetGroupsQuery } from "../../ducks/groups";
import {
  useDeleteTurboSourceRequestMutation,
  useGetTurboSourceRequestsQuery,
  useSubmitTurboSourceRequestMutation,
  type TurboSourceRequest,
  type TurboSourceRequestBody,
} from "../../ducks/turbo_source_requests";
import { useAppDispatch } from "../../types/hooks";
import { parsePosition } from "./parsePosition";

const DEFAULT_RADIUS = "3";
const MAX_RADIUS = 60;
const POLL_MS = 5000;

const STATUS_COLOR = {
  pending: "warning",
  completed: "success",
  failed: "error",
} as const;

const describe = (r: TurboSourceRequest) =>
  r.star ?? `${r.ra?.toFixed(5)} ${r.dec?.toFixed(5)} (${r.radius}")`;

const TurboStarRequestPage = () => {
  const dispatch = useAppDispatch();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"position" | "star">(
    params.get("star") ? "star" : "position",
  );
  const [position, setPosition] = useState(
    params.get("ra") && params.get("dec")
      ? `${params.get("ra")} ${params.get("dec")}`
      : "",
  );
  const [radius, setRadius] = useState(params.get("radius") ?? DEFAULT_RADIUS);
  const [star, setStar] = useState(params.get("star") ?? "");
  const [groupIDs, setGroupIDs] = useState<number[]>([]);

  const groups = useGetGroupsQuery().data?.userAccessible ?? [];
  const { data: requests } = useGetTurboSourceRequestsQuery(undefined, {
    pollingInterval: POLL_MS,
    skipPollingIfUnfocused: true,
  });
  const [submit, { isLoading }] = useSubmitTurboSourceRequestMutation();
  const [remove] = useDeleteTurboSourceRequestMutation();

  const parsed = mode === "position" ? parsePosition(position) : null;
  const radiusValue = Number(radius);
  const radiusOk = radiusValue > 0 && radiusValue <= MAX_RADIUS;
  const positionError = mode === "position" && position !== "" && !parsed;
  const canSubmit =
    mode === "star" ? star.trim() !== "" : parsed !== null && radiusOk;

  const handleSubmit = async () => {
    const body: TurboSourceRequestBody =
      mode === "star"
        ? { star: star.trim() }
        : { ra: parsed!.ra, dec: parsed!.dec, radius: radiusValue };
    if (groupIDs.length > 0) body.group_ids = groupIDs;
    try {
      const result = await submit(body).unwrap();
      dispatch(
        showNotification(
          result.existing
            ? "An identical request is already pending"
            : "Request sent to TURBO",
        ),
      );
    } catch {
      // error notification handled by the base query
    }
  };

  const columns: any[] = [
    {
      field: "created_at",
      headerName: "Requested (UTC)",
      width: 190,
      valueGetter: (_: any, row: TurboSourceRequest) =>
        row.created_at.slice(0, 19).replace("T", " "),
    },
    {
      field: "star",
      headerName: "Request",
      width: 220,
      valueGetter: (_: any, row: TurboSourceRequest) => describe(row),
    },
    {
      field: "status",
      headerName: "Status",
      width: 130,
      renderCell: ({ row }: { row: TurboSourceRequest }) => (
        <Chip
          size="small"
          color={STATUS_COLOR[row.status]}
          label={row.status}
          icon={
            row.status === "pending" ? (
              <CircularProgress size={12} />
            ) : undefined
          }
        />
      ),
    },
    {
      field: "message",
      headerName: "Result",
      flex: 1,
      minWidth: 260,
      renderCell: ({ row }: { row: TurboSourceRequest }) => (
        <span title={row.message ?? ""}>{row.message}</span>
      ),
    },
    {
      field: "obj_id",
      headerName: "Source",
      width: 200,
      renderCell: ({ row }: { row: TurboSourceRequest }) =>
        row.obj_id ? (
          <Link to={`/source/${row.obj_id}`}>{row.obj_id}</Link>
        ) : null,
    },
    {
      field: "delete",
      headerName: " ",
      width: 60,
      sortable: false,
      filterable: false,
      renderCell: ({ row }: { row: TurboSourceRequest }) => (
        <IconButton
          size="small"
          aria-label="Remove from list"
          onClick={() => remove(row.id)}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];

  return (
    <Box sx={{ p: 1, maxWidth: "70rem" }}>
      <Typography variant="h5" gutterBottom>
        Bring a star in from TURBO
      </Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        Most of the stars TURBO measures stay in its own database. Pick one by
        position or by TURBO star ID and it is added here as a source, with
        every point of its light curve.
      </Typography>
      <Paper sx={{ p: 2, mb: 3 }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={mode}
            onChange={(_, value) => value && setMode(value)}
          >
            <ToggleButton value="position">Position</ToggleButton>
            <ToggleButton value="star">Star ID</ToggleButton>
          </ToggleButtonGroup>
          {mode === "position" ? (
            <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
              <TextField
                label="RA Dec"
                placeholder="239.8757 25.9203  or  15:59:30.2 +25:55:13"
                value={position}
                onChange={(e) => setPosition(e.target.value)}
                error={positionError}
                helperText={
                  positionError
                    ? "Not a position: degrees, or sexagesimal with RA in hours"
                    : "Degrees, or sexagesimal with RA in hours"
                }
                sx={{ minWidth: "22rem" }}
              />
              <TextField
                label="Radius (arcsec)"
                value={radius}
                onChange={(e) => setRadius(e.target.value)}
                error={!radiusOk}
                helperText={`Nearest star inside it (up to ${MAX_RADIUS}")`}
                sx={{ width: "11rem" }}
              />
            </Box>
          ) : (
            <TextField
              label="TURBO star ID"
              placeholder="STELLAR26aacljda"
              value={star}
              onChange={(e) => setStar(e.target.value)}
              helperText="The ID of a star source on this site, or from TURBO"
              sx={{ maxWidth: "22rem" }}
            />
          )}
          <Box>
            <GroupShareSelect
              groupList={groups}
              groupIDs={groupIDs}
              setGroupIDs={setGroupIDs}
              maxGroups={3}
            />
            <Typography
              variant="caption"
              component="div"
              color="text.secondary"
            >
              Leave empty to share with the TURBO groups
            </Typography>
          </Box>
          <Box>
            <Button
              primary
              disabled={!canSubmit || isLoading}
              onClick={handleSubmit}
              data-testid="bring_into_skyportal"
            >
              Bring into SkyPortal
            </Button>
          </Box>
        </Box>
      </Paper>
      <Typography variant="h6" gutterBottom>
        Your requests
      </Typography>
      <StyledDataGrid
        autoHeight
        rows={requests ?? []}
        columns={columns}
        getRowId={(row: TurboSourceRequest) => row.id}
        loading={requests === undefined}
        initialState={{
          sorting: { sortModel: [{ field: "created_at", sort: "desc" }] },
        }}
        hideFooter={(requests?.length ?? 0) <= 100}
      />
    </Box>
  );
};

export default TurboStarRequestPage;
