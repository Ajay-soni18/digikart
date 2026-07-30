/* Plays a lecture in a privacy-enhanced (nocookie) YouTube embed. */
import { Modal } from "./ui/Modal";

export function YouTubeModal({ lecture, onClose }) {
  if (!lecture) return null;
  const id = lecture.youtube_video_id;
  return (
    <Modal open={!!lecture} onClose={onClose} title={lecture.title} maxWidth="max-w-3xl">
      <div className="aspect-video w-full overflow-hidden rounded-2xl bg-black">
        {id ? (
          <iframe
            className="h-full w-full"
            src={`https://www.youtube-nocookie.com/embed/${id}?rel=0&modestbranding=1`}
            title={lecture.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        ) : (
          <div className="flex h-full items-center justify-center text-white/70">
            Video unavailable
          </div>
        )}
      </div>
      {lecture.description && (
        <p className="mt-4 text-sm text-ink-soft">{lecture.description}</p>
      )}
    </Modal>
  );
}
