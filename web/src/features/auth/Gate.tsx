import { useMemo, useState, type FormEvent } from 'react';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { IconButton } from '@/components/IconButton';
import { LinearProgress } from '@/components/LinearProgress';
import { TextField } from '@/components/TextField';
import { isValidToken } from '@/api/token';
import { loginQrPayload, qrModel } from '@/lib/qr';
import { useAuth } from './AuthProvider';
import { useQrLogin } from './useQrLogin';

/** The sign-in QR: black on white, 4-module quiet zone, 200 px. */
export function LoginQr({ requestId, size = 200 }: { requestId: string; size?: number }) {
  const model = useMemo(() => {
    try {
      return qrModel(loginQrPayload(window.location.origin, requestId));
    } catch {
      return null;
    }
  }, [requestId]);
  if (!model) return <div className="text-body-m text-error">Could not draw the QR code.</div>;
  const n = model.size + 2 * model.quiet;
  return (
    <svg
      viewBox={`${-model.quiet} ${-model.quiet} ${n} ${n}`}
      width={size}
      height={size}
      shapeRendering="crispEdges"
      role="img"
      aria-label="Sign-in QR code"
      className="rounded-md"
    >
      <rect x={-model.quiet} y={-model.quiet} width={n} height={n} fill="#ffffff" />
      <path d={model.path} fill="#000000" />
    </svg>
  );
}

/**
 * The login gate: centred card with the brand mark, the QR, progress "Waiting for your phone…",
 * instructions, and a text button that reveals the token field.
 */
export function Gate() {
  const { signIn } = useAuth();
  const qr = useQrLogin((token) => void signIn(token));
  const [showToken, setShowToken] = useState(false);
  const [token, setToken] = useState('');
  const [reveal, setReveal] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const candidate = token.trim();
    if (!isValidToken(candidate)) {
      setErr('That token is not valid.');
      return;
    }
    setBusy(true);
    setErr('');
    const ok = await signIn(candidate);
    setBusy(false);
    if (!ok) setErr('That token was not accepted.');
  };

  const waiting =
    qr.phase === 'waiting' || qr.phase === 'hiccup' || qr.phase === 'starting' || qr.phase === 'renewing';

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center overflow-auto bg-surface p-4">
      <div className="w-[400px] max-w-full rounded-2xl bg-card px-8 pt-8 pb-7 shadow-e1 [--field-bg:var(--card)] max-md:px-6">
        <div className="mx-auto mb-4 grid size-14 place-items-center rounded-[18px] bg-primary text-on-primary">
          <Icon name="graphic_eq" size={32} />
        </div>
        <h1 className="m-0 mb-1 text-center font-display text-headline-m text-on-surface">Transom</h1>
        <p className="m-0 mb-6 text-center text-body-m text-on-surface-variant">Sign in with your phone</p>

        {qr.request && qr.phase !== 'unsupported' ? (
          <div className="mx-auto w-[200px]">
            <LoginQr requestId={qr.request.id} />
          </div>
        ) : (
          <div className="mx-auto grid h-[200px] w-[200px] place-items-center rounded-md bg-surface-container-high text-on-surface-variant">
            <Icon name="qr_code" size={32} className="size-11" />
          </div>
        )}
        <div
          className="my-4 mb-2 flex items-center justify-center gap-2.5 text-[13px] text-on-surface-variant"
          role="status"
        >
          {waiting && <LinearProgress className="w-[120px] shrink-0" label="Waiting" />}
          <span className={waiting ? 'whitespace-nowrap' : 'text-center'}>{qr.message}</span>
        </div>
        <p className="m-0 mt-4 mb-5 text-center text-body-m text-on-surface-variant">
          In the Transom app open <b className="font-medium text-on-surface">Settings</b>, tap{' '}
          <b className="font-medium text-on-surface">Sign in on a computer</b> and scan this code.
        </p>

        {!showToken ? (
          <div className="flex justify-center">
            <Button variant="text" onClick={() => setShowToken(true)}>
              Or enter the access token
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-2 flex flex-col gap-3" noValidate>
            <TextField
              label="Access token"
              type={reveal ? 'text' : 'password'}
              autoComplete="current-password"
              autoFocus
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setErr('');
              }}
              error={!!err}
              helper={err || undefined}
              trailing={
                <IconButton
                  icon={reveal ? 'visibility_off' : 'visibility'}
                  label={reveal ? 'Hide token' : 'Show token'}
                  onClick={() => setReveal((v) => !v)}
                  className="-mr-2"
                />
              }
            />
            <Button type="submit" block loading={busy}>
              Sign in
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
