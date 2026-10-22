import { createSortedRowModel, rowSortingFeature, tableFeatures } from "@tanstack/react-table";

/**
 * The table features shared by every table of the app: row sorting.
 *
 * The features object must be stable (module scope) because the table
 * derives its models from it.
 */
export const sortingFeatures = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
});

export type SortingFeatures = typeof sortingFeatures;
