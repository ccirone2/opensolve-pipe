/**
 * Saving a file made in the browser (proposal export.md §5.6). The file is handed to the browser
 * through a Blob URL and a click on an `<a download>`: desktop browsers put it in their
 * downloads, Android Chrome in Downloads with a notification, and iOS Safari (13 and later) asks
 * "Do you want to download …?" and puts it in Files › Downloads. The URL is revoked after 60 s,
 * not at once: some browsers cancel a download whose URL is revoked, and iOS Safari needs it
 * while its prompt is open. Nothing is sent anywhere, and browsers do not report whether the
 * file was kept, so the app says "your browser saves it", never "saved".
 *
 * Not used: showSaveFilePicker (Chromium only), data: URLs (size limits), FileSaver.js (not
 * needed) and Web Share (Later, §10).
 */

/** How long a Blob URL stays valid after its click (ms). */
export const REVOKE_AFTER_MS = 60_000;

/** Hand `blob` to the browser as a download named `fileName`. */
export function saveBlob(blob: Blob, fileName: string): void {
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = fileName;
	link.rel = 'noopener';
	link.hidden = true;
	document.body.append(link);
	try {
		link.click();
	} finally {
		link.remove();
		setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
	}
}

/** A file's size in words: "812 bytes", "28 KB", "1.8 MB" (1 KB = 1000 bytes). */
export function fileSizeText(bytes: number): string {
	if (bytes < 1000) return `${bytes} byte${bytes === 1 ? '' : 's'}`;
	const [value, unit] = bytes < 999_500 ? [bytes / 1e3, 'KB'] : [bytes / 1e6, 'MB'];
	// Two significant figures below 10 (1.8 MB), whole numbers above (28 KB, 234 KB).
	const text = value < 10 ? String(Math.round(value * 10) / 10) : String(Math.round(value));
	return `${text} ${unit}`;
}
