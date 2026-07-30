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
// (The notes viewer pulls in pdf.js — keep it out of the main bundle.)
const Dashboard = lazy(() => import("./pages/Dashboard"));
const SubjectPage = lazy(() => import("./pages/subject/SubjectPage"));
const ChapterLectures = lazy(() => import("./pages/subject/ChapterLectures"));
const ChapterNotes = lazy(() => import("./pages/subject/ChapterNotes"));
const NotesViewer = lazy(() => import("./pages/subject/NotesViewer"));
const Contact = lazy(() => import("./pages/Contact"));
const GeneralPlaylistPage = lazy(() => import("./pages/GeneralPlaylistPage"));
const StaticPage = lazy(() => import("./pages/StaticPage"));
const AdminLayout = lazy(() => import("./admin/AdminLayout"));
const Overview = lazy(() => import("./admin/pages/Overview"));
const Revenue = lazy(() => import("./admin/pages/Revenue"));
const ContentManager = lazy(() => import("./admin/pages/ContentManager"));
const GeneralVideos = lazy(() => import("./admin/pages/GeneralVideos"));
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

          {/* Authenticated (student) */}
          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/playlists/:slug" element={<ProtectedRoute><GeneralPlaylistPage /></ProtectedRoute>} />
          <Route path="/subjects/:slug" element={<ProtectedRoute><SubjectPage /></ProtectedRoute>} />
          <Route
            path="/subjects/:slug/chapters/:chapterId"
            element={<ProtectedRoute><ChapterLectures /></ProtectedRoute>}
          />
          <Route
            path="/subjects/:slug/chapters/:chapterId/notes"
            element={<ProtectedRoute><ChapterNotes /></ProtectedRoute>}
          />
          <Route
            path="/subjects/:slug/notes/:chapterId"
            element={<ProtectedRoute><NotesViewer /></ProtectedRoute>}
          />

          {/* Admin (staff only) */}
          <Route path="/admin" element={<ProtectedRoute adminOnly><AdminLayout /></ProtectedRoute>}>
            <Route index element={<Overview />} />
            <Route path="revenue" element={<Revenue />} />
            <Route path="content" element={<ContentManager />} />
            <Route path="general-videos" element={<GeneralVideos />} />
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
      {/* Persistent notes cart — visible on every page once it has items, so a
          student can gather notes across chapters/subjects/years and pay once. */}
      <CartBar />
      {/* Animated welcome-coupon overlay — self-gates to a signed-in user on the
          dashboard, once per browser session. */}
      <CouponPromoOverlay />
    </>
  );
};

export default App;
