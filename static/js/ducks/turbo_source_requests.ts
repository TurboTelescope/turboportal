/**
 * Requests to bring a star from TURBO's own database into SkyPortal as a
 * source. The TURBO poster serves them and records the outcome on the request.
 */
import { skyportalApi } from "../api/skyportalApi";

export type TurboSourceRequestStatus = "pending" | "completed" | "failed";

export interface TurboSourceRequest {
  id: number;
  created_at: string;
  modified: string;
  requester: string | null;
  allocation_id: number;
  star: string | null;
  ra: number | null;
  dec: number | null;
  radius: number;
  group_ids: number[];
  status: TurboSourceRequestStatus;
  message: string | null;
  obj_id: string | null;
  n_points: number | null;
}

export interface TurboSourceRequestBody {
  star?: string;
  ra?: number;
  dec?: number;
  radius?: number;
  group_ids?: number[];
}

export const turboSourceRequestsApi = skyportalApi.injectEndpoints({
  endpoints: (build) => ({
    getTurboSourceRequests: build.query<TurboSourceRequest[], void>({
      query: () => ({
        url: "api/turbo/source_requests",
        params: { mine: true, limit: 50 },
      }),
      providesTags: ["TurboSourceRequests"],
    }),
    submitTurboSourceRequest: build.mutation<
      { id: number; existing: boolean },
      TurboSourceRequestBody
    >({
      query: (body) => ({
        url: "api/turbo/source_requests",
        method: "POST",
        body,
      }),
      invalidatesTags: ["TurboSourceRequests"],
    }),
    deleteTurboSourceRequest: build.mutation<unknown, number>({
      query: (id) => ({
        url: `api/turbo/source_requests/${id}`,
        method: "DELETE",
      }),
      invalidatesTags: ["TurboSourceRequests"],
    }),
  }),
});

export const {
  useGetTurboSourceRequestsQuery,
  useSubmitTurboSourceRequestMutation,
  useDeleteTurboSourceRequestMutation,
} = turboSourceRequestsApi;
