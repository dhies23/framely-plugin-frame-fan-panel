import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Button, Notice, Section, framely, registerPlugin} from '@framely/sdk';

/* ------------------------------------------------------------------ types */

type Temp = number | null;

interface Snapshot {
  rpm: number | null;
  pwm: number | null;
  mode: 'auto' | 'manual';
  temps: {
    cpu: Temp; gpu: Temp; soc: Temp; ddr: Temp;
    heatsink: Temp; exhaust: Temp;
  };
  stockActive: boolean;
}

interface Status {
  hardware: {supported: boolean; fanPath: string | null; message: string | null};
  daemon: {
    installed: boolean; enabled: boolean; active: boolean;
    pid: number | null; since: string | null; version: string | null; path: string;
  };
  snapshot: Snapshot;
  bundled: string | null;
  unit: {name: string; path: string};
  stock: {name: string; active: boolean};
}

/* ----------------------------------------------------------------- styles */

const css = `
.fan{display:flex;flex-direction:column;gap:18px}
.fan h1{font-size:26px;margin:0}
.fan h1 small{font-weight:400;font-size:16px;color:#acb9cf;margin-left:10px}
.fan .hero{display:flex;gap:14px;align-items:stretch;flex-wrap:wrap}
.fan .card{flex:1 1 150px;background:#18232d;border:1px solid #2c3b4a;border-radius:10px;padding:14px 16px;min-width:140px}
.fan .card .k{font-size:14px;color:#98a8bd}
.fan .card .v{font-size:30px;font-weight:600;line-height:1.25;font-variant-numeric:tabular-nums}
.fan .card .v .u{font-size:15px;font-weight:400;color:#acb9cf;margin-left:4px}
.fan .card.mode-auto .v{color:#8fe3b0}
.fan .card.mode-manual .v{color:#ffd479}
.fan .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:10px}
.fan .cell{background:#18232d;border:1px solid #2c3b4a;border-radius:8px;padding:10px 12px;display:flex;justify-content:space-between;gap:12px;white-space:nowrap}
.fan .cell span:first-child{color:#98a8bd}
.fan .cell span:last-child{font-variant-numeric:tabular-nums}
.fan .cell.hot span:last-child{color:#ff9a8b}
.fan .rows{display:flex;flex-direction:column;gap:8px}
.fan .row{display:flex;gap:10px;justify-content:space-between;align-items:center;background:#18232d;border:1px solid #2c3b4a;border-radius:8px;padding:10px 14px;flex-wrap:wrap}
.fan .row .name{display:flex;gap:10px;align-items:center}
.fan .row code{color:#acb9cf;font-size:15px;overflow-wrap:anywhere}
.fan .badge{border-radius:999px;padding:3px 12px;font-size:15px;white-space:nowrap;background:#2c3b4a;color:#cfd9e6}
.fan .badge.on{background:#1f4d38;color:#8fe3b0}
.fan .badge.off{background:#3a2f22;color:#ffd479}
.fan .badge.dead{background:#442b33;color:#ffc1c6}
.fan .actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.fan .actions button{margin:0}
.fan .danger{background:#5a2a30;border-color:#8c3f47}
.fan .spin{display:inline-block;width:16px;height:16px;border:2px solid #52627a;border-top-color:#edf2fa;border-radius:50%;animation:fan-spin .7s linear infinite;vertical-align:-3px;margin-right:8px}
@keyframes fan-spin{to{transform:rotate(360deg)}}
.fan .foot{color:#7d8ca1;font-size:15px;line-height:1.6}
.fan .hint{color:#acb9cf;font-size:15px;margin:2px 0 0}
`;

/* ------------------------------------------------------------- utilities */

const busyText = (label: string, running: boolean) =>
  running ? <><span className="spin" aria-hidden="true"/>{label}</> : label;

function temp(value: Temp): string {
  return value === null || value === undefined ? '—' : value.toFixed(1) + ' °C';
}

function isHot(value: Temp, limit = 80): boolean {
  return typeof value === 'number' && value >= limit;
}

/* ------------------------------------------------------------------- page */

function StatusRow({name, value}: {name: string; value: React.ReactNode}) {
  return <div className="row"><span className="name">{name}</span><span>{value}</span></div>;
}

function Badge({on, onText, offText}: {on: boolean; onText: string; offText: string}) {
  return <span className={'badge ' + (on ? 'on' : 'off')}>{on ? onText : offText}</span>;
}

function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const [stale, setStale] = useState(false);
  const mounted = useRef(true);
  const received = useRef(0);

  const accept = useCallback((next: Status) => {
    received.current = Date.now();
    setStatus(next);
    setStale(false);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const next = await framely.call<Status>('status');
      if (mounted.current) { accept(next); setError(''); }
    } catch (e) {
      if (mounted.current) setError(String(e).replace(/^Error: /, ''));
    }
  }, [accept]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1500);
    const staleTimer = window.setInterval(() => {
      if (received.current && Date.now() - received.current > 6000) setStale(true);
    }, 1000);
    return () => { mounted.current = false; window.clearInterval(timer); window.clearInterval(staleTimer); };
  }, [refresh]);

  const act = useCallback(async (method: string, label: string) => {
    setBusy(method); setError(''); setNotice('');
    try {
      const result = await framely.call<{message?: string; status?: Status}>(method);
      if (result?.status) accept(result.status); else await refresh();
      setNotice(result?.message ?? label + '完成');
    } catch (e) {
      if (mounted.current) {
        setError(String(e).replace(/^Error: /, ''));
        await refresh();
      }
    } finally {
      if (mounted.current) setBusy('');
    }
  }, [accept, refresh]);

  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = css;
    document.head.append(style);
    return () => style.remove();
  }, []);

  const daemon = status?.daemon;
  const snap = status?.snapshot;
  const supported = status?.hardware.supported ?? true;
  const installed = daemon?.installed ?? false;
  const active = daemon?.active ?? false;
  const enabled = daemon?.enabled ?? false;
  const working = busy !== '';

  return <main className="fan">
    <h1>风扇面板<small>{daemon?.version ? 'v' + daemon.version : ''}</small></h1>

    {status && !supported && <Notice error>{status.hardware.message}</Notice>}
    {stale && <Notice error>后台没有响应，读数可能已经停止刷新。</Notice>}
    {error && <Notice error>{error}</Notice>}
    {notice && !error && <Notice>{notice}</Notice>}

    <section className="hero" aria-label="实时读数">
      <div className="card">
        <div className="k">风扇转速</div>
        <div className="v">{snap?.rpm === null || snap?.rpm === undefined ? '—' : snap.rpm}<span className="u">RPM</span></div>
      </div>
      <div className="card">
        <div className="k">PWM</div>
        <div className="v">{snap?.pwm === null || snap?.pwm === undefined ? '—' : snap.pwm}<span className="u">%</span></div>
      </div>
      <div className={'card mode-' + (snap?.mode ?? 'auto')}>
        <div className="k">当前模式</div>
        <div className="v">{snap ? (snap.mode === 'auto' ? '系统自动' : '手动') : '—'}</div>
      </div>
    </section>

    <Section title="面板状态">
      <div className="rows">
        <StatusRow name="已安装到本机"
          value={<Badge on={installed} onText="已安装" offText="未安装"/>}/>
        <StatusRow name="开机自动启动"
          value={<Badge on={enabled} onText="已启用" offText="已停用"/>}/>
        <StatusRow name="守护进程正在运行"
          value={active
            ? <Badge on onText={daemon?.pid ? '运行中 · PID ' + daemon.pid : '运行中'} offText=""/>
            : <span className="badge dead">已停止</span>}/>
        <StatusRow name="面板版本"
          value={<span>{daemon?.version ?? '—'}{status?.bundled && status.bundled !== daemon?.version
            ? <code>（插件内置 {status.bundled}）</code> : null}</span>}/>
        <StatusRow name="安装位置" value={<code>{daemon?.path}</code>}/>
      </div>

      <div className="actions" style={{marginTop: 14}}>
        {!installed
          ? <Button onClick={() => void act('install', '安装')} disabled={working || !supported}>
              {busyText(installed ? '' : '安装并启用', busy === 'install')}
            </Button>
          : active
            ? <Button onClick={() => void act('disable', '停用')} disabled={working}>
                {busyText('停用', busy === 'disable')}
              </Button>
            : <Button onClick={() => void act('enable', '启用')} disabled={working}>
                {busyText('启用', busy === 'enable')}
              </Button>}
        <Button onClick={() => void refresh()} disabled={working}>{busyText('刷新', busy === 'refresh')}</Button>
        {installed && (confirmUninstall
          ? <>
              <Button className="danger" onClick={() => { setConfirmUninstall(false); void act('uninstall', '卸载'); }}
                disabled={working}>{busyText('确认卸载', busy === 'uninstall')}</Button>
              <Button onClick={() => setConfirmUninstall(false)} disabled={working}>取消</Button>
            </>
          : <Button className="danger" onClick={() => setConfirmUninstall(true)} disabled={working}>卸载</Button>)}
      </div>
      <p className="hint">
        停用只会停止面板并把风扇交回系统温控，文件保留；卸载会一并删除程序与 systemd 服务。
      </p>
    </Section>

    <Section title="温度">
      <div className="grid">
        {([['CPU', snap?.temps.cpu], ['GPU', snap?.temps.gpu], ['SoC 最高', snap?.temps.soc],
           ['内存 DDR', snap?.temps.ddr], ['散热鳍片', snap?.temps.heatsink],
           ['出风口', snap?.temps.exhaust]] as [string, Temp][])
          .map(([label, value]) =>
            <div className={'cell' + (isHot(value) ? ' hot' : '')} key={label}>
              <span>{label}</span><span>{temp(value)}</span>
            </div>)}
      </div>
      <p className="hint">
        SoC 达到 88 °C 时，风扇面板会自己交回系统温控；手动调速最低只能到 20 %，再低风扇会停转。
      </p>
    </Section>

    <Section title="调用方式">
      <div className="rows">
        <StatusRow name="systemd 服务" value={<code>{status?.unit.name ?? '—'}</code>}/>
        <StatusRow name="系统温控" value={<Badge on={status?.stock.active ?? false} onText="运行中" offText="已停用"/>}/>
      </div>
      <p className="foot" style={{marginTop: 12}}>
        调节界面仍然在 SteamVR 的快捷菜单里（手柄电池图标 → 风扇标签页）。这个页面只负责安装、启用、停用和查看状态。
      </p>
    </Section>
  </main>;
}

registerPlugin({QuickPage: App});
