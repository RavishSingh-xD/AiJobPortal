import { Amplify } from "aws-amplify";
import {
  signUp,
  confirmSignUp,
  resendSignUpCode,
  resetPassword,
  confirmResetPassword,
  signIn,
  signOut as amplifySignOut,
  getCurrentUser,
  fetchAuthSession,
  fetchUserAttributes,
} from "aws-amplify/auth";

const amplifyConfig = {
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_COGNITO_APP_CLIENT_ID,
      loginWith: { email: true },
    },
  },
};

Amplify.configure(amplifyConfig);

function isUsernameExistsError(err) {
  const name = err?.name || err?.code || "";
  const message = String(err?.message || "").toLowerCase();
  return (
    name === "UsernameExistsException" ||
    name === "AliasExistsException" ||
    message.includes("already exists") ||
    message.includes("user already exists")
  );
}

export class PendingVerificationError extends Error {
  constructor(email, message) {
    super(message);
    this.name = "PendingVerificationError";
    this.email = email;
  }
}

async function clearUnconfirmedSignup(email) {
  const apiUrl = import.meta.env.VITE_API_URL;
  if (!apiUrl) {
    return { action: "skipped" };
  }

  try {
    const res = await fetch(`${apiUrl}/auth/retry-signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (res.status === 404) {
      return { action: "skipped" };
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { action: "skipped" };
    }
    return data;
  } catch {
    return { action: "skipped" };
  }
}

async function redirectPendingVerification(email) {
  try {
    await resendSignUpCode({ username: email });
  } catch {
    // Still route to verify — user can tap Resend on that page
  }
  throw new PendingVerificationError(
    email,
    "This email has a pending signup. Enter the verification code we emailed you (check spam too)."
  );
}

export async function registerUser(email, password, name) {
  const normalizedEmail = email.trim().toLowerCase();

  const attemptSignUp = () =>
    signUp({
      username: normalizedEmail,
      password,
      options: {
        userAttributes: {
          email: normalizedEmail,
          name,
        },
      },
    });

  try {
    return await attemptSignUp();
  } catch (err) {
    if (!isUsernameExistsError(err)) {
      throw err;
    }

    const recovery = await clearUnconfirmedSignup(normalizedEmail);

    if (recovery.action === "deleted" || recovery.action === "not_found") {
      return await attemptSignUp();
    }

    if (recovery.action === "confirmed") {
      throw new Error(
        "An account with this email already exists. Log in instead."
      );
    }

    return redirectPendingVerification(normalizedEmail);
  }
}

export async function verifyOtp(email, code) {
  return confirmSignUp({
    username: email,
    confirmationCode: code,
  });
}

export async function resendSignupCode(email) {
  return resendSignUpCode({ username: email });
}

export async function requestPasswordReset(email) {
  return resetPassword({ username: email });
}

export async function confirmPasswordReset(email, code, newPassword) {
  return confirmResetPassword({
    username: email,
    confirmationCode: code,
    newPassword,
  });
}

export async function loginUser(email, password) {
  try {
    const existingUser = await getCurrentUser();
    if (existingUser) {
      await amplifySignOut();
    }
  } catch {
    // No existing session to clear
  }

  return signIn({
    username: email,
    password,
  });
}

export async function signOut() {
  return amplifySignOut();
}

export async function logoutUser() {
  return signOut();
}

export async function getIdToken() {
  try {
    const session = await fetchAuthSession();
    const idToken = session.tokens?.idToken;
    if (!idToken) {
      return null;
    }
    return idToken.toString();
  } catch {
    return null;
  }
}

export async function getAuthenticatedUser() {
  return getCurrentUser();
}

export async function getAccessToken() {
  const session = await fetchAuthSession();
  return session.tokens?.idToken?.toString() ?? null;
}

export async function getUserProfile() {
  const attributes = await fetchUserAttributes();
  const profile = {
    userId: attributes.sub,
    email: attributes.email,
    name: attributes.name,
    verificationType: attributes["custom:verification_type"],
    verificationStatus: attributes["custom:verification_status"],
    collegeName: attributes["custom:college_name"],
  };

  // DynamoDB is the source of truth for verification; Cognito can lag after OCR.
  const apiUrl = import.meta.env.VITE_API_URL;
  if (apiUrl) {
    try {
      const token = await getIdToken();
      if (token) {
        const res = await fetch(`${apiUrl}/profile`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          if (data.verificationStatus) {
            profile.verificationStatus = data.verificationStatus;
          }
          if (data.verificationType) {
            profile.verificationType = data.verificationType;
          }
        }
      }
    } catch {
      // Keep Cognito attributes when profile API is unavailable
    }
  }

  return profile;
}
