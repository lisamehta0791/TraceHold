import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement> & { size?: number };
const base = (size = 18): SVGProps<SVGSVGElement> => ({
  width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
  strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round',
});

export const IconLens = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5 21 21" /><path d="M7.5 9.2a3.4 3.4 0 0 1 2.6-2.2" /></svg>
);
export const IconHome = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><path d="M3 11 12 4l9 7" /><path d="M5 10v9.5h14V10" /><path d="M10 19.5v-5h4v5" /></svg>
);
export const IconDashboard = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><rect x="3.5" y="3.5" width="7" height="9" rx="1.6" /><rect x="13.5" y="3.5" width="7" height="5" rx="1.6" /><rect x="13.5" y="11.5" width="7" height="9" rx="1.6" /><rect x="3.5" y="15.5" width="7" height="5" rx="1.6" /></svg>
);
export const IconCases = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><path d="M4 6.5h16M4 12h16M4 17.5h10" /><circle cx="18.5" cy="17.5" r="2" /></svg>
);
export const IconFlask = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><path d="M9.5 3.5h5M10.5 3.5v6L5 19a1.3 1.3 0 0 0 1.1 2h11.8A1.3 1.3 0 0 0 19 19l-5.5-9.5v-6" /><path d="M7.5 15h9" /></svg>
);
export const IconScale = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><path d="M12 3.5v17M7 20.5h10M5 7h14" /><path d="M5 7 2.5 13a2.5 2.5 0 0 0 5 0L5 7ZM19 7l-2.5 6a2.5 2.5 0 0 0 5 0L19 7Z" /></svg>
);
export const IconInsights = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><path d="M3.5 20.5h17" /><path d="M5 16l4.5-5 3.5 3 6-7.5" /><circle cx="19" cy="6.5" r="1.4" /></svg>
);
export const IconEngine = ({ size, ...p }: P) => (
  <svg {...base(size)} {...p}><circle cx="12" cy="12" r="3.2" /><path d="M12 2.8v2.6M12 18.6v2.6M21.2 12h-2.6M5.4 12H2.8M18.5 5.5l-1.8 1.8M7.3 16.7l-1.8 1.8M18.5 18.5l-1.8-1.8M7.3 7.3 5.5 5.5" /></svg>
);
export const IconChevron = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="m9 6 6 6-6 6" /></svg>);
export const IconChevronLeft = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="m15 6-6 6 6 6" /></svg>);
export const IconSearch = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>);
export const IconCheck = ({ size, ...p }: P) => (<svg {...base(size)} strokeWidth={2.4} {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>);
export const IconX = ({ size, ...p }: P) => (<svg {...base(size)} strokeWidth={2.2} {...p}><path d="M6 6l12 12M18 6 6 18" /></svg>);
export const IconAlert = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M12 3.8 2.8 19.5h18.4L12 3.8Z" /><path d="M12 10v4.2M12 17h.01" /></svg>);
export const IconConflict = ({ size, ...p }: P) => (<svg {...base(size)} strokeWidth={2.2} {...p}><path d="M7 7l4 5-4 5M17 7l-4 5 4 5" /></svg>);
export const IconCopy = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="8.5" y="8.5" width="11" height="11" rx="2" /><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5" /></svg>);
export const IconDownload = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M12 4v11M7 10.5l5 5 5-5M4.5 19.5h15" /></svg>);
export const IconExternal = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4.5a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1H10" /></svg>);
export const IconRefresh = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" /><path d="M19.5 4.5v4h-4" /></svg>);
export const IconPlay = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M7 4.8v14.4L19 12 7 4.8Z" fill="currentColor" /></svg>);
export const IconPlus = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M12 5v14M5 12h14" /></svg>);
export const IconTrash = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5" /></svg>);
export const IconCamera = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M3.5 12a8.5 8.5 0 1 0 2.5-6" /><path d="M3.5 4v4h4" /></svg>);
export const IconDoc = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M6 3.5h8l4 4v13H6z" /><path d="M14 3.5v4h4M9 12h6M9 15.5h6" /></svg>);
export const IconUser = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><circle cx="12" cy="8.5" r="3.8" /><path d="M4.5 20a7.5 7.5 0 0 1 15 0" /></svg>);
export const IconShield = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M12 3.5 4.5 6.5V12c0 4.5 3.2 7.6 7.5 8.5 4.3-.9 7.5-4 7.5-8.5V6.5L12 3.5Z" /><path d="m8.8 12 2.2 2.2 4.2-4.4" /></svg>);
export const IconHand = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M8 12V5.5a1.5 1.5 0 0 1 3 0V11M11 10V4a1.5 1.5 0 0 1 3 0v6.5M14 10.5V6a1.5 1.5 0 0 1 3 0v7.5c0 4-2.5 7-6.5 7-2.5 0-4-1.2-5.3-3.2L3.5 14a1.5 1.5 0 0 1 2.5-1.6L8 15" /></svg>);
export const IconClock = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>);
export const IconDb = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><ellipse cx="12" cy="6" rx="7" ry="2.5" /><path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" /></svg>);
export const IconMenu = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M4 7h16M4 12h16M4 17h16" /></svg>);
export const IconSink = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M4 9h16l-2 9.5H6L4 9Z" /><path d="M12 3v8M9 8l3 3 3-3" /></svg>);
export const IconAsk = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M4.5 5.5h15v10h-8l-4.5 3.5v-3.5H4.5z" /><path d="M10 9.2a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9v.4M12 14h.01" /></svg>);
export const IconLetter = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="3.5" y="5.5" width="17" height="13" rx="1.5" /><path d="m4 6.5 8 6 8-6" /></svg>);
export const IconSpark = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M12 3.5 13.8 9l5.7 1.5-5.7 1.6L12 17.5l-1.8-5.4-5.7-1.6L10.2 9 12 3.5Z" /><path d="M18.5 16.5l.7 2 2 .6-2 .7-.7 2-.6-2-2-.7 2-.6.6-2Z" /></svg>);
