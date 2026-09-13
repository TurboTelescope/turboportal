/**
 * Difference-image cutouts behind a source's photometry points, requested one
 * point (or one view of the plot) at a time and rendered asynchronously.
 */
import { skyportalApi } from "../api/skyportalApi";

export type PhotometryCutoutStatus = "pending" | "ready" | "failed";
export type PhotometryCutoutRequestStatus = "pending" | "ready" | "unavailable";

export interface PhotometryCutout {
  photometry_id: number;
  status: PhotometryCutoutStatus;
  public_url: string | null;
  error: string | null;
  stale: boolean;
}

export const photometryCutoutsApi = skyportalApi.injectEndpoints({
  endpoints: (build) => ({
    getPhotometryCutouts: build.query<PhotometryCutout[], string>({
      query: (objId) => ({ url: `api/sources/${objId}/photometry_cutouts` }),
      providesTags: ["PhotometryCutouts"],
    }),
    requestPhotometryCutouts: build.mutation<
      { statuses: Record<string, PhotometryCutoutRequestStatus> },
      { objId: string; photometryIds: number[] }
    >({
      query: ({ objId, photometryIds }) => ({
        url: `api/sources/${objId}/photometry_cutouts`,
        method: "POST",
        body: { photometry_ids: photometryIds },
      }),
      invalidatesTags: ["PhotometryCutouts"],
    }),
  }),
});

export const {
  useGetPhotometryCutoutsQuery,
  useRequestPhotometryCutoutsMutation,
} = photometryCutoutsApi;
