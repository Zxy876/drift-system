package com.driftmc.cinematic;

/**
 * Marker interface for individual cinematic actions.
 */
public interface CinematicAction {

    /**
     * Execute the action. Implementations must invoke {@code onComplete.run()} once their
     * work has finished so that the controller can continue to the next step in the
     * sequence.
     */
    void play(CinematicContext context, Runnable onComplete);
}
