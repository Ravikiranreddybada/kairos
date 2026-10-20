import { Copies } from "./components/Copies";
import { Masthead } from "./components/Masthead";
import { MobilePad, Pad } from "./components/Pad";
import { RequisitionForm } from "./components/RequisitionForm";
import { usePad } from "./store";

export function App() {
  const { pad, current, busy, submit, open, newPad } = usePad();
  const padProps = { items: pad.items, openId: pad.openId, sessionId: pad.sessionId, busy, onOpen: open, onNewPad: newPad };

  return (
    <div className="grid h-full grid-rows-[56px_minmax(0,1fr)]">
      <Masthead />
      <main
        className="grid min-h-0 overflow-y-auto lg:grid-cols-[248px_minmax(0,1fr)] lg:grid-rows-[auto_1fr]
          xl:grid-cols-[248px_minmax(0,1fr)_440px] xl:grid-rows-1 xl:overflow-hidden"
      >
        <aside
          aria-label="Requisition pad"
          className="hidden border-r border-rule-strong bg-ground-2 lg:row-span-2 lg:block xl:row-span-1 xl:overflow-y-auto"
        >
          <Pad {...padProps} />
        </aside>

        <section aria-label="Open requisition" className="min-w-0 px-4 pt-4 pb-8 sm:px-6 lg:px-8 xl:overflow-y-auto">
          <MobilePad {...padProps} />
          <RequisitionForm
            key={current?.id ?? "blank"}
            req={current}
            sessionId={pad.sessionId}
            nextNo={pad.nextNo}
            busy={busy}
            onSubmit={submit}
            onNew={() => open(null)}
          />
        </section>

        <section
          aria-label="Copies"
          className="min-w-0 px-4 pb-10 sm:px-6 lg:col-start-2 lg:px-8 xl:col-start-3 xl:row-start-1 xl:overflow-y-auto
            xl:border-l xl:border-rule-strong xl:bg-ground-2 xl:px-5 xl:pt-4"
        >
          <Copies req={current} />
        </section>
      </main>
    </div>
  );
}
