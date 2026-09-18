/**
 * @file llscriptautomationlistener.h
 * @brief Permission-preserving LEAP API for task LSL inspection and updates.
 *
 * $LicenseInfo:firstyear=2026&license=viewerlgpl$
 * Copyright (C) 2026, The Phoenix Firestorm Project, Inc.
 * $/LicenseInfo$
 */

#ifndef LL_LLSCRIPTAUTOMATIONLISTENER_H
#define LL_LLSCRIPTAUTOMATIONLISTENER_H

#include "lleventapi.h"

class LLUUID;

// The viewer already has one global ScriptRunningReply handler. Forward every
// reply into the automation event pump so a coroutine can preserve the
// script's running state and VM target without replacing that handler.
void postScriptAutomationRunningReply(const LLUUID& object_id,
                                      const LLUUID& item_id,
                                      bool running,
                                      bool mono);

class LLScriptAutomationListener final : public LLEventAPI
{
public:
    LLScriptAutomationListener();

private:
    void getTaskInventory(const LLSD& request) const;
    void getScriptSource(const LLSD& request) const;
    void updateScriptSource(const LLSD& request) const;
};

#endif // LL_LLSCRIPTAUTOMATIONLISTENER_H
