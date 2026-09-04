/**
 * Forced-photometry DIF cutouts for a source.
 *
 * Requesting them goes through the existing TURBO forced-photometry follow-up
 * form (the "DIF cutouts" checkbox); these endpoints only read back and clear
 * what the poster has attached.
 */
import { skyportalApi } from "../api/skyportalApi";

export interface FPCutout {
  id: number;
  photometry_id: number | null;
  public_url: string | null;
}

export const fpCutoutsApi = skyportalApi.injectEndpoints({
  endpoints: (build) => ({
    fpCutouts: build.query<FPCutout[], string>({
      query: (objId) => ({ url: `api/sources/${objId}/fp_cutouts` }),
      providesTags: ["FPCutouts"],
    }),
    deleteFPCutouts: build.mutation<{ deleted: number }, string>({
      query: (objId) => ({
        url: `api/sources/${objId}/fp_cutouts`,
        method: "DELETE",
      }),
      invalidatesTags: ["FPCutouts"],
    }),
  }),
});

export const { useFpCutoutsQuery, useDeleteFPCutoutsMutation } = fpCutoutsApi;
