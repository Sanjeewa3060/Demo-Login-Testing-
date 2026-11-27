import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./session";
import Login from "./pages/Login";
import Portal from "./pages/Portal";
import Product from "./pages/Product";
import Admin from "./pages/Admin";
import Report from "./pages/Report";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/portal" element={<RequireAuth><Portal /></RequireAuth>} />
      <Route path="/fms" element={<RequireAuth><Product kind="fms" /></RequireAuth>} />
      <Route path="/pos" element={<RequireAuth><Product kind="pos" /></RequireAuth>} />
      <Route path="/ecommerce" element={<RequireAuth><Product kind="ecommerce" /></RequireAuth>} />
      <Route path="/ems" element={<RequireAuth><Product kind="ems" /></RequireAuth>} />
      <Route path="/admin" element={<RequireAuth><Admin /></RequireAuth>} />
      <Route path="/report" element={<Report />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
