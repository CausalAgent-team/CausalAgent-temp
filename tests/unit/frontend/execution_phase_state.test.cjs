const test = require('node:test');
const assert = require('node:assert/strict');

const phaseState = require('../../../app/static/js/execution_phase_state.js');

test('history replay accepts node events but rejects message side effects', () => {
    assert.equal(phaseState.isHistoryEvent('node_start'), true);
    assert.equal(phaseState.isHistoryEvent('tool_call_result'), true);
    assert.equal(phaseState.isHistoryEvent('text_delta'), false);
    assert.equal(phaseState.isHistoryEvent('final_result'), false);
    assert.equal(phaseState.isHistoryEvent('interrupt'), false);
});

test('only queued and running phases resume an SSE subscription', () => {
    assert.equal(phaseState.isActivePhase('queued'), true);
    assert.equal(phaseState.isActivePhase('running'), true);
    assert.equal(phaseState.isActivePhase('waiting_input'), false);
    assert.equal(phaseState.isActivePhase('completed'), false);
});

test('active API metadata cannot advance the rendered event cursor', () => {
    const merged = phaseState.mergeActiveJob(
        { rendered_event_id: 12, last_event_id: 12, thinkingElements: {} },
        { status: 'running', last_event_id: 18 },
    );

    assert.equal(merged.status, 'running');
    assert.equal(merged.last_event_id, 12);
    assert.equal(merged.rendered_event_id, 12);
});

test('step details that arrive before their parent are deferred and replayed once', () => {
    const pending = new Map();
    const event = { type: 'decision', step_id: 'deep-step', summary: '选择 PC' };

    assert.equal(phaseState.deferStepEvent(pending, event, { historyMode: true }), true);
    assert.deepEqual(phaseState.takeDeferredStepEvents(pending, 'deep-step'), [{
        eventData: event,
        renderOptions: { historyMode: true },
    }]);
    assert.deepEqual(phaseState.takeDeferredStepEvents(pending, 'deep-step'), []);
});

test('only live decisions animate and reduced motion is respected', () => {
    assert.equal(phaseState.shouldAnimateDecision(), true);
    assert.equal(phaseState.shouldAnimateDecision({ historyMode: true }), false);
    assert.equal(phaseState.shouldAnimateDecision({ reducedMotion: true }), false);
});

test('parallel decision animations are started serially', () => {
    const queue = phaseState.createSerialTaskQueue();
    const started = [];
    let finishFirst;
    let finishSecond;

    queue.enqueue(done => {
        started.push('first');
        finishFirst = done;
    });
    queue.enqueue(done => {
        started.push('second');
        finishSecond = done;
    });

    assert.deepEqual(started, ['first']);
    finishFirst();
    assert.deepEqual(started, ['first', 'second']);
    finishSecond();
});
