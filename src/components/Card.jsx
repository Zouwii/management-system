export default function Card({ children, className = '' }) {
  return (
    <div className={`rounded-3xl border border-slate-200/90 bg-white/94 shadow-[0_24px_50px_-26px_rgba(15,23,42,0.38),0_10px_20px_-16px_rgba(71,85,105,0.18)] backdrop-blur-sm ${className}`}>
      {children}
    </div>
  );
}
