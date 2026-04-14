import { Navigate, Route, Routes } from "react-router-dom";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { InboxPage } from "./pages/InboxPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<InboxPage />} />
      <Route path="/cases/:caseId" element={<CaseDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
