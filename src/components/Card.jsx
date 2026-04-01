export default function Card({ children, className = '' }) {
  return (
    <div className={`rounded-3xl border border-slate-300/80 bg-white shadow-[0_24px_50px_-26px_rgba(15,23,42,0.34),0_12px_22px_-18px_rgba(71,85,105,0.14)] ${className}`}>
      {children}
    </div>
  );
}
