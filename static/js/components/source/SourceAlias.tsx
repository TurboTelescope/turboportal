import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AddIcon from "@mui/icons-material/Add";
import IconButton from "@mui/material/IconButton";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import { makeStyles } from "tss-react/mui";
import SaveIcon from "@mui/icons-material/Save";
import TextField from "@mui/material/TextField";

import { showNotification } from "baselayer/components/Notifications";
import { useAppDispatch } from "../../types/hooks";
import Button from "../Button";
import FormValidationError from "../FormValidationError";
import { useUpdateSourceMutation } from "../../ducks/source";

const useStyles = makeStyles()(() => ({
  container: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: "0.4rem",
  },
  chip: {
    maxWidth: "100%",
  },
  none: {
    fontStyle: "italic",
    opacity: 0.6,
  },
  addButton: {
    opacity: 0.5,
    transition: "opacity 0.2s",
    "&:hover": {
      opacity: 1,
    },
  },
  saveButton: {
    textAlign: "center",
    margin: "1rem",
  },
}));

// Our own TURBO and STELLAR ids are sources here; ZTF ids open in ALeRCE.
const aliasLabel = (alias: string) => {
  if (/^(TURBO|STELLAR)\d{2}[a-z]{7}$/.test(alias)) {
    return <Link to={`/source/${alias}`}>{alias}</Link>;
  }
  if (/^ZTF\d{2}[a-z]{7}$/.test(alias)) {
    return (
      <a
        href={`https://alerce.online/object/${alias}`}
        target="_blank"
        rel="noopener noreferrer"
      >
        {alias}
      </a>
    );
  }
  return alias;
};

interface SourceAliasProps {
  source: {
    id: string;
    alias?: string[];
  };
}

const SourceAlias = ({ source }: SourceAliasProps) => {
  const { classes } = useStyles();
  const dispatch = useAppDispatch();
  const [updateSource] = useUpdateSourceMutation();
  const [alias, setAlias] = useState<string | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [invalid, setInvalid] = useState(true);

  useEffect(() => {
    // Invalid when empty or a duplicate of an existing alias.
    setInvalid(!alias || !!source?.alias?.includes(alias));
  }, [source, setInvalid, alias]);

  const handleChange = (e: any) => {
    setAlias(e.target.value);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    const newAliasList = [...(source.alias || []), alias];
    try {
      await updateSource({
        id: source.id,
        payload: { alias: newAliasList },
      }).unwrap();
      dispatch(showNotification("Source alias successfully updated."));
      setDialogOpen(false);
      setAlias(null);
    } catch {
      // error notification handled by the baseQuery
    }
    setIsSubmitting(false);
  };

  const handleDelete = async (aliasToDelete: string) => {
    setIsSubmitting(true);
    const newAliasList = (source.alias || []).filter(
      (a) => a !== aliasToDelete,
    );

    try {
      await updateSource({
        id: source.id,
        payload: { alias: newAliasList },
      }).unwrap();
      dispatch(showNotification("Source alias removed successfully."));
    } catch {
      // error notification handled by the baseQuery
    }
    setIsSubmitting(false);
  };

  const aliases = source.alias || [];

  return (
    <>
      <div className={classes.container}>
        <b>Aliases:</b>
        {aliases.length === 0 && <span className={classes.none}>none</span>}
        {aliases.map((a, idx) => (
          <Chip
            key={`${a}-${idx}`}
            className={classes.chip}
            label={aliasLabel(a)}
            size="small"
            variant="outlined"
            onDelete={() => handleDelete(a)}
          />
        ))}
        <Tooltip title="Add alias">
          <IconButton
            data-testid="updateAliasIconButton"
            onClick={() => setDialogOpen(true)}
            size="small"
            className={classes.addButton}
          >
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </div>
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)}>
        <DialogTitle>Add Alias</DialogTitle>
        <DialogContent>
          <div>
            {invalid && (
              <FormValidationError message="Please enter a new alias" />
            )}
            <TextField
              data-testid="addAliasTextfield"
              size="small"
              label="alias"
              name="alias"
              onChange={handleChange}
              type="string"
              variant="outlined"
            />
          </div>
          <div className={classes.saveButton}>
            <Button
              secondary
              onClick={() => {
                handleSubmit();
              }}
              endIcon={<SaveIcon />}
              size="large"
              data-testid="addAliasSubmitButton"
              disabled={isSubmitting || invalid}
            >
              Save
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default SourceAlias;
