import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./app/AppShell";
import { LoginPage } from "./auth/LoginPage";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { ScanPage } from "./tracking/ScanPage";
import { CategoriesPage } from "./catalog/CategoriesPage";
import { TypesPage } from "./catalog/TypesPage";
import { VendorsPage } from "./catalog/VendorsPage";
import { LocationsPage } from "./locations/LocationsPage";
import { AssetListPage } from "./assets/AssetListPage";
import { AssetFormPage } from "./assets/AssetFormPage";
import { AssetDetailPage } from "./assets/AssetDetailPage";

function Protected({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute>
      <AppShell>{children}</AppShell>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route path="/" element={<Navigate to="/assets" replace />} />

      <Route
        path="/scan"
        element={
          <Protected>
            <div className="max-w-3xl mx-auto">
              <ScanPage />
            </div>
          </Protected>
        }
      />

      <Route
        path="/assets"
        element={
          <Protected>
            <AssetListPage />
          </Protected>
        }
      />
      <Route
        path="/assets/new"
        element={
          <Protected>
            <AssetFormPage />
          </Protected>
        }
      />
      <Route
        path="/assets/:assetId"
        element={
          <Protected>
            <AssetDetailPage />
          </Protected>
        }
      />
      <Route
        path="/assets/:assetId/edit"
        element={
          <Protected>
            <AssetFormPage />
          </Protected>
        }
      />

      <Route
        path="/catalog/categories"
        element={
          <Protected>
            <CategoriesPage />
          </Protected>
        }
      />
      <Route
        path="/catalog/types"
        element={
          <Protected>
            <TypesPage />
          </Protected>
        }
      />
      <Route
        path="/catalog/vendors"
        element={
          <Protected>
            <VendorsPage />
          </Protected>
        }
      />

      <Route
        path="/locations"
        element={
          <Protected>
            <LocationsPage />
          </Protected>
        }
      />

      <Route path="*" element={<Navigate to="/assets" replace />} />
    </Routes>
  );
}

export default App;
