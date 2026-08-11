import axios from "axios";
import { getIdToken } from "./authService";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use(async (config) => {
  const token = await getIdToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function requestUploadUrl(userId, fileType) {
  const { data } = await api.post("/verification/upload-url", {
    userId,
    fileType,
  });
  return data;
}

export async function uploadFileToS3(uploadUrl, file) {
  await axios.put(uploadUrl, file, {
    headers: { "Content-Type": "image/jpeg" },
  });
}

export default api;
