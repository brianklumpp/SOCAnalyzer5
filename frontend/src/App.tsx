
import React from "react";
import Router from "./router";
import { SplitViewProvider } from "./contexts/SplitViewContext";
import { AuthProvider } from "./contexts/AuthContext";
import SessionTimeoutWarning from "./components/auth/SessionTimeoutWarning";

function App() {
  return (
    <AuthProvider>
      <SplitViewProvider>
        <SessionTimeoutWarning warningMinutes={5} checkIntervalSeconds={30} />
        <Router />
      </SplitViewProvider>
    </AuthProvider>
  );
}

export default App;
