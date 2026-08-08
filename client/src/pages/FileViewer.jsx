/*
 * Full-screen reader for a PROTECTED file.
 *
 * Wraps PdfViewer in ProtectedContent (the anti-capture layer) and hands it
 * both ids it needs: `fileId` addresses the bytes, `productId` is what a page
 * bookmark points at. Access is enforced by the backend on the signed-URL call
 * — this component only decides what to render.
 */
import { FiArrowLeft } from "react-icons/fi";
import { AppHeader } from "../components/AppHeader";
import { PdfViewer } from "../components/pdf/PdfViewer";
import { ProtectedContent } from "../components/ProtectedContent";
import { Button } from "../components/ui/Button";

export function FileViewer({ file, productId, title, onClose }) {
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-extrabold text-ink">{title}</h1>
            <p className="truncate text-sm text-muted">{file.title}</p>
          </div>
          <Button variant="secondary" size="sm" icon={FiArrowLeft} onClick={onClose}>
            Back
          </Button>
        </div>

        <div className="rounded-card bg-surface shadow-card ring-1 ring-brand-100">
          <ProtectedContent>
            <PdfViewer fileId={file.id} productId={productId} version={file.version} />
          </ProtectedContent>
        </div>
      </main>
    </div>
  );
}
