import { AnimatePresence, MotionConfig } from 'motion/react';
import { lazy, Suspense, useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { NavRail } from './components/NavRail';
import { TopBar } from './components/TopBar';
import { Page } from './components/Page';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PageSkeleton } from './components/Skeleton';
import Analyze from './pages/Analyze';
import Cases from './pages/Cases';
import LienReview from './pages/LienReview';
import System from './pages/System';
import NotFound from './pages/NotFound';

// Larger pages are split into their own chunks.
const Landing = lazy(() => import('./pages/Landing'));
const CaseDetail = lazy(() => import('./pages/CaseDetail'));
const Ask = lazy(() => import('./pages/Ask'));

const COLLAPSE_KEY = 'tracehold.rail.collapsed';

export default function App() {
  const location = useLocation();
  useEffect(() => { window.scrollTo({ top: 0 }); }, [location.pathname]);

  return (
    <MotionConfig reducedMotion="user">
      {location.pathname === '/' ? (
        <ErrorBoundary title="The home page could not be shown.">
          <Suspense fallback={<div className="landing-loading" />}>
            <Landing />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <AppShell />
      )}
    </MotionConfig>
  );
}

/** The working application: navigation rail, top bar and the analysis pages. */
function AppShell() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) === '1'; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0'); } catch { /* ignore */ }
  }, [collapsed]);

  return (
    <div className={`app ${collapsed ? 'collapsed' : ''}`}>
      <NavRail collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
      <div className="main">
        <TopBar />
        <AnimatePresence mode="wait" initial={false}>
          <Page key={location.pathname}>
            <ErrorBoundary key={location.pathname} title="This page could not be shown.">
            <Suspense fallback={<PageSkeleton />}>
              <Routes location={location}>
                <Route path="/analyze" element={<Analyze />} />
                <Route path="/cases" element={<Cases />} />
                <Route path="/cases/:id" element={<CaseDetail />} />
                <Route path="/lien-review" element={<LienReview />} />
                <Route path="/ask" element={<Ask />} />
                <Route path="/system" element={<System />} />
                <Route path="/dashboard" element={<Navigate to="/cases" replace />} />
                <Route path="/worked-example" element={<Navigate to="/analyze" replace />} />
                <Route path="/insights" element={<Navigate to="/system" replace />} />
                <Route path="/engine" element={<Navigate to="/system" replace />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </Suspense>
            </ErrorBoundary>
          </Page>
        </AnimatePresence>
      </div>
      <div className="footer-badge" title="Every account, case and transaction in TraceHold is generated synthetically">
        <b>●</b> Synthetic data
      </div>
    </div>
  );
}
