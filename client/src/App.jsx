import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { FullScreenLoader } from "./components/ui/Spinner";
import ScrollToTop from "./components/ScrollToTop";
import { CartBar } from "./components/CartBar";
import { CouponPromoOverlay } from "./components/CouponPromoOverlay";

// Eager: tiny, always-needed entry pages.
import Landing from "./pages/Landing";
import Login from "./pages/auth/Login";
import Signup from "./pages/auth/Signup";

// Lazy: split heavier / less-frequent routes into their own chunks.
// (The product page pulls in pdf.js via the viewer — keep it out of the main bundle.)
const Dashboard = lazy(() => import("./pages/Dashboard"));
const CategoryPage = lazy(() => import("./pages/CategoryPage"));
const ProductPage = lazy(() => import("./pages/ProductPage"));
const Contact = lazy(() => import("./pages/Contact"));
const StaticPage = lazy(() => import("./pages/StaticPage"));
const AdminLayout = lazy(() => import("./admin/AdminLayout"));
const Overview = lazy(() => import("./admin/pages/Overview"));
const Revenue = lazy(() => import("./admin/pages/Revenue"));
const CatalogManager = lazy(() => import("./admin/pages/CatalogManager"));
const Bundles = lazy(() => import("./admin/pages/Bundles"));
const SiteContentEditor = lazy(() => import("./admin/pages/SiteContentEditor"));
const Users = lazy(() => import("./admin/pages/Users"));
const Announcements = lazy(() => import("./admin/pages/Announcements"));
const Coupons = lazy(() => import("./admin/pages/Coupons"));
const ContactInbox = lazy(() => import("./admin/pages/ContactInbox"));

const App = () => {
  return (
    <>
      {/* Reset window scroll to the top on every route change (declarative
          React Router does not do this on its own). */}
      <ScrollToTop />
      <Suspense fallback={<FullScreenLoader />}>
        <Routes>
          {/* Public */}
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/about" element={<StaticPage title="About Us" field="about_us" />} />
          <Route path="/privacy" element={<StaticPage title="Privacy Policy" field="privacy_policy" />} />
          <Route path="/disclaimer" element={<StaticPage title="Disclaimer" field="disclaimer" />} />

          {/* Authenticated (buyer) */}
          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/c/:slug" element={<ProtectedRoute><CategoryPage /></ProtectedRoute>} />
          <Route path="/p/:slug" element={<ProtectedRoute><ProductPage /></ProtectedRoute>} />

          {/* Admin */}
          <Route path="/admin" element={<ProtectedRoute adminOnly><AdminLayout /></ProtectedRoute>}>
            <Route index element={<Overview />} />
            <Route path="revenue" element={<Revenue />} />
            <Route path="catalog" element={<CatalogManager />} />
            <Route path="bundles" element={<Bundles />} />
            <Route path="coupons" element={<Coupons />} />
            <Route path="announcements" element={<Announcements />} />
            <Route path="messages" element={<ContactInbox />} />
            <Route path="site" element={<SiteContentEditor />} />
            <Route path="users" element={<Users />} />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      {/* Persistent cart — visible on every page once it has items, so a buyer
          can gather products across the catalog and pay once. */}
      <CartBar />
      {/* Animated welcome-coupon overlay — self-gates to a signed-in user on the
          dashboard, once per browser session. */}
      <CouponPromoOverlay />
    </>
  );
};

export default App;
