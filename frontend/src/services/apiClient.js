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

export async function listJobs(domain, options = {}) {
  const { data } = await api.get("/jobs", {
    params: { domain, ...options },
  });
  return data;
}

export async function listSubdomains(domain) {
  const { data } = await api.get("/jobs", {
    params: { domain, listSubdomains: true },
  });
  return data;
}

export async function startMatchSession() {
  const { data } = await api.post("/match/start");
  return data;
}

export async function requestResumeUploadUrl(sessionId, payload) {
  const { data } = await api.post(
    `/match/${sessionId}/resume-upload-url`,
    payload
  );
  return data;
}

export async function getMatchSession(sessionId) {
  const { data } = await api.get(`/match/${sessionId}`);
  return data;
}

export async function startDomainTest(sessionId, payload) {
  const { data } = await api.post(`/match/${sessionId}/test/start`, payload);
  return data;
}

export async function submitTestAnswer(sessionId, payload) {
  const { data } = await api.post(`/match/${sessionId}/test/answer`, payload);
  return data;
}

export async function getMatchedJobs(sessionId) {
  const { data } = await api.get(`/match/${sessionId}/matches`);
  return data;
}

export async function getFinalRecommendation(sessionId) {
  const { data } = await api.post(`/match/${sessionId}/recommendation`);
  return data;
}

export async function createApplication(payload) {
  const { data } = await api.post("/applications", payload);
  return data;
}

export async function listApplications() {
  const { data } = await api.get("/applications");
  return data;
}

export async function saveJob(payload) {
  const { data } = await api.post("/saved-jobs", payload);
  return data;
}

export async function listSavedJobs() {
  const { data } = await api.get("/saved-jobs");
  return data;
}

export async function unsaveJob(canonicalId) {
  const { data } = await api.delete("/saved-jobs", {
    params: { canonicalId },
  });
  return data;
}

export async function getProfile() {
  const { data } = await api.get("/profile");
  return data;
}

export async function updateProfile(payload) {
  const { data } = await api.put("/profile", payload);
  return data;
}

export async function createSavedSearch(payload) {
  const { data } = await api.post("/saved-searches", payload);
  return data;
}

export async function listSavedSearches() {
  const { data } = await api.get("/saved-searches");
  return data;
}

export async function deleteSavedSearch(searchId) {
  const { data } = await api.delete("/saved-searches", {
    params: { searchId },
  });
  return data;
}

export async function getSavedSearchAlerts() {
  const { data } = await api.get("/saved-searches/alerts");
  return data;
}

export async function ackSavedSearch(searchId, canonicalIds) {
  const { data } = await api.post("/saved-searches/ack", {
    searchId,
    canonicalIds,
  });
  return data;
}

export async function compareJobs(payload) {
  const { data } = await api.post("/jobs/compare", payload);
  return data;
}

export async function uploadFileToS3(uploadUrl, file) {
  const contentType = file.type || "image/jpeg";
  await axios.put(uploadUrl, file, {
    headers: { "Content-Type": contentType },
  });
}

export async function uploadResumeToS3(uploadUrl, file) {
  const contentType =
    file.type ||
    (file.name.toLowerCase().endsWith(".docx")
      ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      : "application/pdf");
  await axios.put(uploadUrl, file, {
    headers: { "Content-Type": contentType },
  });
}

export default api;
