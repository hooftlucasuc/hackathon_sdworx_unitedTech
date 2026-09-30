import { useState } from 'react';
import { ESCALATION_THRESHOLD, type Call, type Caller, type Company } from '../types';
import { CallerBanner } from './CallerBanner';
import { ChatLog } from './Conversation';
import { ErrorBoundary } from './ErrorBoundary';
import { AskNow, useQuestions } from './NextQuestions';
import { BestMatches, OfferSolution, useTopSuggestions } from './Solutions';

interface Props {
  call: Call;
  caller: Caller | null | undefined;
  company: Company | null | undefined;
  callerCalls: Call[] | undefined;
  isNew: boolean;
}

/**
 * One call: the conversation on top, what to say now at the bottom. The bottom switches from
 * "Ask now" to the solution once nothing is left to ask, when the call ends, or on request.
 */
export function CallView({ call, caller, company, callerCalls, isNew }: Props) {
  const live = call.status === 'live';
  const questions = useQuestions(call);
  const { top5, solutions } = useTopSuggestions(call);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [offerNow, setOfferNow] = useState(false);

  const nothingLeftToAsk = questions.questions !== undefined && questions.questions.length === 0;
  const offer = !live || nothingLeftToAsk || offerNow;
  const hasCandidate = (top5[0]?.score ?? 0) >= ESCALATION_THRESHOLD;
  const shownId =
    call.chosen_solution_id ??
    (pickedId && top5.some((s) => s.solution_id === pickedId) ? pickedId : (top5[0]?.solution_id ?? null));

  return (
    <>
      <ErrorBoundary label="Caller">
        <CallerBanner call={call} caller={caller} company={company} callerCalls={callerCalls} isNew={isNew} />
      </ErrorBoundary>

      <div className="call-layout">
        <div className="chat-col">
          <ErrorBoundary label="Conversation">
            <ChatLog call={call} />
          </ErrorBoundary>
          <ErrorBoundary key={offer ? 'offer' : 'ask'} label={offer ? 'Solution' : 'Ask now'}>
            {offer ? (
              <OfferSolution
                call={call}
                top5={top5}
                solutions={solutions}
                shownId={shownId}
                onBack={live && !nothingLeftToAsk ? () => setOfferNow(false) : undefined}
              />
            ) : (
              <AskNow state={questions} onOffer={hasCandidate ? () => setOfferNow(true) : undefined} />
            )}
          </ErrorBoundary>
        </div>

        <aside className="side-col">
          <ErrorBoundary label="Best matches">
            <BestMatches
              top5={top5}
              solutions={solutions}
              live={live}
              shownId={offer ? shownId : null}
              onSelect={(id) => {
                setPickedId(id);
                setOfferNow(true);
              }}
            />
          </ErrorBoundary>
        </aside>
      </div>
    </>
  );
}
