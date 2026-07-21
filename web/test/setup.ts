import "@testing-library/jest-dom/vitest";

process.env.NEXT_PUBLIC_COURT4_API_URL = "http://localhost:8000";
process.env.NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES = "1073741824";
process.env.NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS = ".mp4,.mov,.avi,.mkv";
