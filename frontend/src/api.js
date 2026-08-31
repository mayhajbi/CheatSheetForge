// עטיפה דקה לקריאות ה-API. ב-dev הבקשות עוברות דרך ה-proxy ב-vite.config.js.
// ב-production (Railway) יש להגדיר VITE_API_BASE_URL כמשתנה סביבה של הבילד.

const BASE = import.meta.env.VITE_API_BASE_URL || "";

// שגיאת שרת לא תמיד מגיעה כ-JSON (למשל 500 מ-uvicorn מחזיר טקסט), ולכן
// אסור לקרוא res.json() בעיוורון -- אחרת המשתמש מקבל "Unexpected token"
// במקום הסיבה האמיתית.
async function readError(res, fallback) {
  const body = await res.text();
  try {
    return JSON.parse(body).detail || fallback;
  } catch {
    return `${fallback} (${res.status}): ${body.slice(0, 200)}`;
  }
}

export async function uploadFiles({ course, maxPages, examFiles, syllabusFile }) {
  const formData = new FormData();
  formData.append("course", course);
  formData.append("max_pages", String(maxPages));
  examFiles.forEach((f) => formData.append("exam_files", f));
  formData.append("syllabus_file", syllabusFile);

  const res = await fetch(`${BASE}/api/upload`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res, "העלאה נכשלה"));
  return res.json();
}

export async function mergeSession(sessionId) {
  const res = await fetch(`${BASE}/api/merge/${sessionId}`, { method: "POST" });
  if (!res.ok) throw new Error(await readError(res, "איחוד נכשל"));
  return res.json();
}

export async function removeItems(sessionId, itemIndices) {
  const res = await fetch(`${BASE}/api/preview/${sessionId}/remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(itemIndices),
  });
  if (!res.ok) throw new Error(await readError(res, "הסרה נכשלה"));
  return res.json();
}

export async function exportBank(sessionId, format, fontName, fontSizePt) {
  const params = new URLSearchParams({ format, font_name: fontName, font_size_pt: String(fontSizePt) });
  const res = await fetch(`${BASE}/api/export/${sessionId}?${params}`, { method: "POST" });
  if (!res.ok) throw new Error(await readError(res, "ייצוא נכשל"));
  return res.blob();
}

export async function deleteSession(sessionId) {
  await fetch(`${BASE}/api/session/${sessionId}`, { method: "DELETE" });
}
