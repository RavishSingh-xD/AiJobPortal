/**
 * Users with rejected OCR/ID verification must re-complete verify-id
 * before using the app. Manual signups pending review also go to verify-id.
 */
export function requiresIdentityVerification(profile) {
  if (!profile) {
    return false;
  }
  const status = profile.verificationStatus;
  if (status === "rejected") {
    return true;
  }
  if (status === "pending_review" && profile.verificationType === "manual") {
    return true;
  }
  return false;
}

export function getPostLoginPath(profile) {
  if (requiresIdentityVerification(profile)) {
    return "/verify-id";
  }
  return "/dashboard";
}
