import { FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { config } from "../../config";
import { useAuth } from "../../shared/auth/AuthProvider";
import { Button } from "../../shared/ui/Button";
import { Card } from "../../shared/ui/Card";

export function LoginPage() {
  const auth = useAuth();
  const location = useLocation();
  const [token, setToken] = useState("");
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? "/dashboard";

  if (auth.isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const submitDevToken = (event: FormEvent) => {
    event.preventDefault();
    auth.setDevToken(token.trim());
  };

  return (
    <main className="auth-page">
      <Card>
        <p className="eyebrow">Secure inventory workspace</p>
        <h1>Sign in to Inventory and Expiry Mgt</h1>
        <p>
          Use your organization identity provider. The API validates OIDC access
          tokens and provisions users without storing passwords.
        </p>
        {config.authMode === "dev-token" ? (
          <form onSubmit={submitDevToken} className="stack">
            <label className="field">
              <span>Development bearer token</span>
              <textarea
                value={token}
                onChange={(event) => setToken(event.target.value)}
                rows={5}
                placeholder="Paste a local test JWT"
              />
            </label>
            <Button type="submit">Use token</Button>
          </form>
        ) : (
          <Button onClick={() => void auth.login()}>Continue with SSO</Button>
        )}
      </Card>
    </main>
  );
}
