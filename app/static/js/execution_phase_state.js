(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.ExecutionPhaseState = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    const HISTORY_EVENT_TYPES = new Set([
        'node_start', 'progress', 'decision', 'tool_call_start',
        'tool_call_result', 'node_retry', 'node_end',
    ]);
    const ACTIVE_PHASE_STATUSES = new Set(['queued', 'running']);

    function isHistoryEvent(type) {
        return HISTORY_EVENT_TYPES.has(type);
    }

    function isActivePhase(status) {
        return ACTIVE_PHASE_STATUSES.has(status);
    }

    function mergeActiveJob(existing, incoming) {
        const merged = { ...(existing || {}), ...(incoming || {}) };
        if (existing && existing.rendered_event_id !== undefined) {
            merged.rendered_event_id = Number(existing.rendered_event_id || 0);
            merged.last_event_id = merged.rendered_event_id;
        }
        return merged;
    }

    function deferStepEvent(pendingEvents, eventData, renderOptions = {}) {
        const stepId = eventData && eventData.step_id;
        if (!stepId) return false;
        const events = pendingEvents.get(stepId) || [];
        events.push({ eventData, renderOptions });
        pendingEvents.set(stepId, events);
        return true;
    }

    function takeDeferredStepEvents(pendingEvents, stepId) {
        const events = pendingEvents.get(stepId) || [];
        pendingEvents.delete(stepId);
        return events;
    }

    function shouldAnimateDecision({ historyMode = false, reducedMotion = false } = {}) {
        return !historyMode && !reducedMotion;
    }

    function createSerialTaskQueue() {
        const pending = [];
        let running = false;

        function startNext() {
            if (running || pending.length === 0) return;
            running = true;
            const task = pending.shift();
            let completed = false;
            const complete = () => {
                if (completed) return;
                completed = true;
                running = false;
                startNext();
            };
            try {
                task(complete);
            } catch (error) {
                complete();
                throw error;
            }
        }

        return {
            enqueue(task) {
                if (typeof task !== 'function') return false;
                pending.push(task);
                startNext();
                return true;
            },
        };
    }

    return {
        isHistoryEvent,
        isActivePhase,
        mergeActiveJob,
        deferStepEvent,
        takeDeferredStepEvents,
        shouldAnimateDecision,
        createSerialTaskQueue,
    };
});
