import { rel } from "@/lib/api";

export const folder = rel.split("/")[0] ?? "";
export const folderUrl = "/" + folder + "/";
export const folderPages = (folder.length <= 3 ? folder.toUpperCase() : folder.slice(0, 1).toUpperCase() + folder.slice(1)) + " pages";
