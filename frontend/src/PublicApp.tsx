import { RegistrarCodeRegistrationPage, ScoringPage } from "./WorkspacePages";

function PublicApp() {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/register") return <RegistrarCodeRegistrationPage />;
  if (path === "/score") return <ScoringPage />;
  return (
    <main className="workspace-page">
      <h1>Страница не найдена</h1>
      <p>Публичная зона доступна только для регистрации и ввода баллов.</p>
    </main>
  );
}

export default PublicApp;
