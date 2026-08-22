/** User-facing messages for resume upload / scoring failures from the match API. */

export const RESUME_REJECTED_MESSAGE =
  "This file does not appear to be a resume. Please upload your CV (PDF or DOCX) with your education and work experience.";

export function formatResumeScoringError(message) {
  if (!message || typeof message !== "string") {
    return "Scoring failed. Please try again.";
  }
  if (message.includes("does not appear to be a resume")) {
    return RESUME_REJECTED_MESSAGE;
  }
  if (message === "Unsupported or unreadable resume file") {
    return "Could not read that file. Upload a PDF or DOCX resume.";
  }
  if (message === "Could not read resume text") {
    return "That file looks empty or unreadable. Try a different PDF or DOCX export.";
  }
  return message;
}
