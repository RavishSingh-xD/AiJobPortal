export function apiErrorMessage(err, fallback) {
  const data = err.response?.data;
  if (data && typeof data === "object") {
    if (typeof data.error === "string" && data.error) {
      return data.error;
    }
    if (data.errors && typeof data.errors === "object") {
      const parts = Object.entries(data.errors)
        .filter(([, message]) => message != null && message !== "")
        .map(([field, message]) => `${field}: ${message}`);
      if (parts.length) {
        return parts.join("; ");
      }
    }
  }
  return err.message || fallback;
}
