/**
 * @file llscriptautomationlistener.cpp
 * @brief Permission-preserving LEAP API for task LSL inspection and updates.
 *
 * $LicenseInfo:firstyear=2026&license=viewerlgpl$
 * Copyright (C) 2026, The Phoenix Firestorm Project, Inc.
 * $/LicenseInfo$
 */

#include "llviewerprecompiledheaders.h"

#include "llscriptautomationlistener.h"

#include "llagent.h"
#include "llassetstorage.h"
#include "llcoros.h"
#include "lleventcoro.h"
#include "lleventfilter.h"
#include "llexperiencecache.h"
#include "llfilesystem.h"
#include "llsdutil.h"
#include "message.h"
#include "llviewerassetupload.h"
#include "llviewerinventory.h"
#include "llviewerobject.h"
#include "llviewerobjectlist.h"
#include "llviewerregion.h"
#include "llvoinventorylistener.h"
#include "roles_constants.h"
#include "rlvhandler.h"
#include "rlvlocks.h"

#include <memory>

namespace
{
constexpr F32 INVENTORY_TIMEOUT_SECONDS = 30.f;
constexpr F32 ASSET_TIMEOUT_SECONDS = 60.f;
constexpr F32 RUNTIME_TIMEOUT_SECONDS = 30.f;
constexpr F32 EXPERIENCE_TIMEOUT_SECONDS = 30.f;
constexpr F32 UPLOAD_TIMEOUT_SECONDS = 120.f;
constexpr size_t MAX_SCRIPT_SOURCE_BYTES = 64 * 1024;
constexpr char SCRIPT_RUNTIME_PUMP[] = "LLScriptAutomationRunningReply";

void post_reply(const LLSD& request, LLSD reply)
{
    if (!request.has("reply"))
    {
        return;
    }

    LLReqID(request).stamp(reply);
    LLEventPumps::instance().obtain(request["reply"]).post(reply);
}

void post_error(const LLSD& request, const std::string& message)
{
    LLSD reply;
    reply["error"] = message;
    post_reply(request, reply);
}

class TaskInventoryFetcher final : public LLVOInventoryListener
{
public:
    using ptr_t = std::shared_ptr<TaskInventoryFetcher>;

    TaskInventoryFetcher(LLEventPump& pump, LLViewerObject* object)
        : mPump(pump)
    {
        registerVOInventoryListener(object, nullptr);
    }

    void fetch()
    {
        requestVOInventory();
    }

    const LLInventoryObject::object_list_t& inventory() const
    {
        return mInventory;
    }

    void inventoryChanged(LLViewerObject*,
                          LLInventoryObject::object_list_t* inventory,
                          S32,
                          void*) override
    {
        mInventory.clear();
        if (inventory)
        {
            mInventory.assign(inventory->begin(), inventory->end());
        }
        removeVOInventoryListener();
        mPump.post(LLSDMap("changed", true));
    }

private:
    LLEventPump& mPump;
    LLInventoryObject::object_list_t mInventory;
};

bool fetch_task_inventory(LLViewerObject* object,
                          LLInventoryObject::object_list_t& inventory,
                          std::string& error)
{
    LLEventMailDrop maildrop("LLScriptAutomationInventory", true);
    TaskInventoryFetcher::ptr_t fetcher =
        std::make_shared<TaskInventoryFetcher>(maildrop, object);
    fetcher->fetch();

    LLSD result = llcoro::suspendUntilEventOnWithTimeout(
        maildrop,
        INVENTORY_TIMEOUT_SECONDS,
        LLSDMap("timeout", true));
    if (result.has("timeout"))
    {
        error = "Timed out while fetching object task inventory";
        return false;
    }

    inventory.assign(fetcher->inventory().begin(), fetcher->inventory().end());
    return true;
}

LLViewerInventoryItem* find_script_item(
    const LLInventoryObject::object_list_t& inventory,
    const LLUUID& item_id)
{
    for (const LLPointer<LLInventoryObject>& object : inventory)
    {
        if (object.notNull() && object->getUUID() == item_id)
        {
            LLViewerInventoryItem* item =
                dynamic_cast<LLViewerInventoryItem*>(object.get());
            if (item && item->getType() == LLAssetType::AT_LSL_TEXT)
            {
                return item;
            }
            return nullptr;
        }
    }
    return nullptr;
}

bool validate_script_access(LLViewerObject* object,
                            LLViewerInventoryItem* item,
                            std::string& error)
{
    if (!object || !item)
    {
        error = "The object or script is no longer available";
        return false;
    }
    if (!object->permModify() && !gAgent.isGodlike())
    {
        error = "The logged-in avatar cannot modify this object";
        return false;
    }
    if (object->isAttachment() && rlv_handler_t::isEnabled() &&
        gRlvAttachmentLocks.isLockedAttachment(object->getRootEdit()))
    {
        error = "The attachment is locked by RLVa";
        return false;
    }

    const LLPermissions& permissions = item->getPermissions();
    const bool can_copy = gAgent.allowOperation(
        PERM_COPY, permissions, GP_OBJECT_MANIPULATE);
    const bool can_modify = gAgent.allowOperation(
        PERM_MODIFY, permissions, GP_OBJECT_MANIPULATE);
    if (!gAgent.isGodlike() && (!can_copy || !can_modify))
    {
        error = "The logged-in avatar cannot view and modify this script source";
        return false;
    }
    return true;
}

struct ScriptAssetRequest
{
    explicit ScriptAssetRequest(std::string pump_name)
        : pump(std::move(pump_name))
    {
    }

    std::string pump;
};

void script_asset_loaded(const LLUUID& asset_id,
                         LLAssetType::EType type,
                         void* user_data,
                         S32 status,
                         LLExtStat)
{
    std::unique_ptr<ScriptAssetRequest> context(
        static_cast<ScriptAssetRequest*>(user_data));
    LLSD result;

    if (status != LL_ERR_NOERR)
    {
        result["error"] = llformat(
            "Firestorm could not retrieve the script source (status %d)", status);
    }
    else
    {
        LLFileSystem file(asset_id, type);
        const S32 length = file.getSize();
        if (length < 0 || static_cast<size_t>(length) > MAX_SCRIPT_SOURCE_BYTES)
        {
            result["error"] = "The retrieved script source has an invalid size";
        }
        else
        {
            std::vector<U8> buffer(static_cast<size_t>(length));
            if (length > 0)
            {
                file.read(buffer.data(), length);
            }
            if (file.getLastBytesRead() != length)
            {
                result["error"] = "Firestorm could not read the retrieved script source";
            }
            else
            {
                // Task-script assets normally include one trailing C-string
                // terminator. The live editor ignores it when loading the
                // cached asset; do the same here without accepting a NUL as
                // actual script content.
                if (!buffer.empty() && buffer.back() == '\0')
                {
                    buffer.pop_back();
                }

                if (std::find(buffer.begin(), buffer.end(), '\0') != buffer.end())
                {
                    result["error"] =
                        "The retrieved script source contains an embedded NUL byte";
                }
                else
                {
                    result["source"] = buffer.empty()
                        ? std::string()
                        : std::string(
                              reinterpret_cast<const char*>(buffer.data()),
                              buffer.size());
                    result["asset_id"] = asset_id;
                }
            }
        }
    }

    LLEventPumps::instance().obtain(context->pump).post(result);
}

bool load_script_source(LLViewerObject* object,
                        LLViewerInventoryItem* item,
                        std::string& source,
                        std::string& error)
{
    if (!gAssetStorage || !object->getRegion())
    {
        error = "Firestorm cannot access the script asset service for this object";
        return false;
    }

    LLEventMailDrop maildrop("LLScriptAutomationAsset", true);
    auto* context = new ScriptAssetRequest(maildrop.getName());

    gAssetStorage->getInvItemAsset(
        object->getRegion()->getHost(),
        gAgent.getID(),
        gAgent.getSessionID(),
        item->getPermissions().getOwner(),
        object->getID(),
        item->getUUID(),
        item->getAssetUUID(),
        item->getType(),
        &script_asset_loaded,
        context,
        true);

    LLSD result = llcoro::suspendUntilEventOnWithTimeout(
        maildrop,
        ASSET_TIMEOUT_SECONDS,
        LLSDMap("timeout", true));
    if (result.has("timeout"))
    {
        // Asset storage owns the callback context and may still call it later.
        error = "Timed out while retrieving script source";
        return false;
    }
    if (result.has("error"))
    {
        error = result["error"].asString();
        return false;
    }

    source = result["source"].asString();
    return true;
}

bool get_script_runtime(LLViewerObject* object,
                        LLViewerInventoryItem* item,
                        bool& running,
                        LLScriptAssetUpload::TargetType_t& target,
                        std::string& error)
{
    if (!gMessageSystem || !object || !object->getRegion())
    {
        error = "Firestorm cannot query the script runtime state";
        return false;
    }

    LLEventPump& replies = LLEventPumps::instance().obtain(SCRIPT_RUNTIME_PUMP);
    LLEventMatching matching(
        replies,
        LLSDMap("object_id", object->getID())("item_id", item->getUUID()));

    gMessageSystem->newMessageFast(_PREHASH_GetScriptRunning);
    gMessageSystem->nextBlockFast(_PREHASH_Script);
    gMessageSystem->addUUIDFast(_PREHASH_ObjectID, object->getID());
    gMessageSystem->addUUIDFast(_PREHASH_ItemID, item->getUUID());
    gMessageSystem->sendReliable(object->getRegion()->getHost());

    LLSD result = llcoro::suspendUntilEventOnWithTimeout(
        matching,
        RUNTIME_TIMEOUT_SECONDS,
        LLSDMap("timeout", true));
    if (result.has("timeout"))
    {
        error = "Timed out while querying the script runtime state";
        return false;
    }

    running = result["running"].asBoolean();
    target = result["mono"].asBoolean()
        ? LLScriptAssetUpload::MONO
        : LLScriptAssetUpload::LSL2;
    return true;
}

bool get_script_experience(LLViewerObject* object,
                           LLViewerInventoryItem* item,
                           LLUUID& experience_id,
                           std::string& error)
{
    experience_id.setNull();
    LLViewerRegion* region = object ? object->getRegion() : nullptr;
    const std::string url = region
        ? region->getCapability("GetMetadata")
        : std::string();
    if (url.empty())
    {
        // OpenSim regions commonly have no Experiences metadata capability.
        return true;
    }

    LLEventMailDrop maildrop("LLScriptAutomationExperience", true);
    const std::string pump_name = maildrop.getName();
    LLExperienceCache::instance().fetchAssociatedExperience(
        object->getID(),
        item->getUUID(),
        url,
        [pump_name](const LLSD& result)
        {
            LLEventPumps::instance().obtain(pump_name).post(result);
        });

    LLSD result = llcoro::suspendUntilEventOnWithTimeout(
        maildrop,
        EXPERIENCE_TIMEOUT_SECONDS,
        LLSDMap("timeout", true));
    if (result.has("timeout"))
    {
        error = "Timed out while querying the script experience";
        return false;
    }
    if (result.has(LLExperienceCache::EXPERIENCE_ID))
    {
        experience_id = result[LLExperienceCache::EXPERIENCE_ID].asUUID();
        return true;
    }
    if (result["error"].asInteger() == -1 &&
        result["message"].asString() == "no experience")
    {
        return true;
    }

    error = result.has("message")
        ? "Firestorm could not determine the script experience: " +
              result["message"].asString()
        : "Firestorm could not determine the script experience";
    return false;
}

bool resolve_script(const LLSD& request,
                    LLPointer<LLViewerObject>& object,
                    LLInventoryObject::object_list_t& inventory,
                    LLViewerInventoryItem*& item,
                    std::string& error)
{
    const LLUUID object_id = request["object_id"].asUUID();
    const LLUUID item_id = request["item_id"].asUUID();
    if (object_id.isNull() || item_id.isNull())
    {
        error = "object_id and item_id must be non-null UUIDs";
        return false;
    }

    object = gObjectList.findObject(object_id);
    if (object.isNull())
    {
        error = "The object is not currently available to the viewer";
        return false;
    }
    if (!fetch_task_inventory(object, inventory, error))
    {
        return false;
    }

    item = find_script_item(inventory, item_id);
    if (!item)
    {
        error = "The requested LSL script is not in this object's task inventory";
        return false;
    }
    return validate_script_access(object, item, error);
}

void get_task_inventory_coro(LLSD request)
{
    const LLUUID object_id = request["object_id"].asUUID();
    if (object_id.isNull())
    {
        return post_error(request, "object_id must be a non-null UUID");
    }

    LLPointer<LLViewerObject> object = gObjectList.findObject(object_id);
    if (object.isNull())
    {
        return post_error(request, "The object is not currently available to the viewer");
    }
    if (!object->permModify() && !gAgent.isGodlike())
    {
        return post_error(request, "The logged-in avatar cannot inspect this object's task inventory");
    }

    LLInventoryObject::object_list_t inventory;
    std::string error;
    if (!fetch_task_inventory(object, inventory, error))
    {
        return post_error(request, error);
    }

    LLSD reply;
    reply["object_id"] = object_id;
    reply["items"] = LLSD::emptyArray();
    for (const LLPointer<LLInventoryObject>& inventory_object : inventory)
    {
        LLViewerInventoryItem* item = inventory_object.notNull()
            ? dynamic_cast<LLViewerInventoryItem*>(inventory_object.get())
            : nullptr;
        if (!item)
        {
            continue;
        }

        const LLPermissions& permissions = item->getPermissions();
        LLSD entry;
        entry["item_id"] = item->getUUID();
        entry["name"] = item->getName();
        entry["description"] = item->getDescription();
        entry["asset_type"] = LLAssetType::lookup(item->getType());
        entry["inventory_type"] = LLInventoryType::lookup(item->getInventoryType());
        entry["is_script"] = item->getType() == LLAssetType::AT_LSL_TEXT;
        entry["can_copy"] = gAgent.allowOperation(
            PERM_COPY, permissions, GP_OBJECT_MANIPULATE);
        entry["can_modify"] = gAgent.allowOperation(
            PERM_MODIFY, permissions, GP_OBJECT_MANIPULATE);
        entry["can_transfer"] = gAgent.allowOperation(
            PERM_TRANSFER, permissions, GP_OBJECT_MANIPULATE);
        reply["items"].append(entry);
    }
    post_reply(request, reply);
}

void get_script_source_coro(LLSD request)
{
    LLPointer<LLViewerObject> object;
    LLInventoryObject::object_list_t inventory;
    LLViewerInventoryItem* item = nullptr;
    std::string error;
    if (!resolve_script(request, object, inventory, item, error))
    {
        return post_error(request, error);
    }

    std::string source;
    if (!load_script_source(object, item, source, error))
    {
        return post_error(request, error);
    }

    LLSD reply;
    reply["object_id"] = object->getID();
    reply["item_id"] = item->getUUID();
    reply["name"] = item->getName();
    reply["source"] = source;
    reply["bytes"] = LLSD::Integer(static_cast<S32>(source.size()));
    post_reply(request, reply);
}

void update_script_source_coro(LLSD request)
{
    LLPointer<LLViewerObject> object;
    LLInventoryObject::object_list_t inventory;
    LLViewerInventoryItem* item = nullptr;
    std::string error;
    if (!resolve_script(request, object, inventory, item, error))
    {
        return post_error(request, error);
    }

    const std::string source = request["source"].asString();
    if (source.size() > MAX_SCRIPT_SOURCE_BYTES)
    {
        return post_error(request, "Script source exceeds the 64 KiB safety limit");
    }
    if (source.find('\0') != std::string::npos)
    {
        return post_error(request, "Script source cannot contain a NUL byte");
    }

    bool running = false;
    LLScriptAssetUpload::TargetType_t target = LLScriptAssetUpload::MONO;
    if (!get_script_runtime(object, item, running, target, error))
    {
        return post_error(request, error);
    }

    LLUUID experience_id;
    if (!get_script_experience(object, item, experience_id, error))
    {
        return post_error(request, error);
    }

    LLViewerRegion* region = object->getRegion();
    const std::string url = region
        ? region->getCapability("UpdateScriptTask")
        : std::string();
    if (url.empty())
    {
        return post_error(request, "The region does not expose UpdateScriptTask");
    }

    LLEventMailDrop maildrop("LLScriptAutomationUpload", true);
    const std::string pump_name = maildrop.getName();
    LLBufferedAssetUploadInfo::taskUploadFinish_f finish =
        [pump_name](LLUUID item_id, LLUUID task_id, LLUUID, LLSD response)
        {
            response["item_id"] = item_id;
            response["object_id"] = task_id;
            LLEventPumps::instance().obtain(pump_name).post(response);
        };
    LLBufferedAssetUploadInfo::uploadFailed_f failed =
        [pump_name](LLUUID item_id, LLUUID task_id, LLSD response, std::string reason)
        {
            response["item_id"] = item_id;
            response["object_id"] = task_id;
            response["error"] = reason.empty()
                ? "Firestorm could not upload the script"
                : reason;
            LLEventPumps::instance().obtain(pump_name).post(response);
            return true;
        };

    LLResourceUploadInfo::ptr_t upload = std::make_shared<LLScriptAssetUpload>(
        object->getID(),
        item->getUUID(),
        target,
        running,
        experience_id,
        source,
        finish,
        failed);
    LLViewerAssetUpload::EnqueueInventoryUpload(url, upload);

    LLSD result = llcoro::suspendUntilEventOnWithTimeout(
        maildrop,
        UPLOAD_TIMEOUT_SECONDS,
        LLSDMap("timeout", true));
    if (result.has("timeout"))
    {
        return post_error(request, "Timed out while compiling and uploading the script");
    }
    if (result.has("error"))
    {
        return post_error(request, result["error"].asString());
    }

    LLSD reply;
    reply["object_id"] = object->getID();
    reply["item_id"] = item->getUUID();
    reply["compiled"] = result["compiled"].asBoolean();
    reply["installed"] = result["compiled"].asBoolean();
    reply["running"] = running;
    reply["target"] = target == LLScriptAssetUpload::MONO ? "mono" : "lsl2";
    reply["errors"] = result.has("errors")
        ? result["errors"]
        : LLSD::emptyArray();
    post_reply(request, reply);
}
} // namespace

LLScriptAutomationListener::LLScriptAutomationListener()
    : LLEventAPI(
          "LLScriptAutomation",
          "Permission-preserving task inventory and LSL source operations")
{
    add("getTaskInventory",
        "Fetch task inventory for [\"object_id\"] and return [\"items\"]",
        &LLScriptAutomationListener::getTaskInventory,
        llsd::map("object_id", LLSD(), "reply", LLSD()));
    add("getScriptSource",
        "Fetch permitted LSL source for [\"object_id\"] and [\"item_id\"]",
        &LLScriptAutomationListener::getScriptSource,
        llsd::map("object_id", LLSD(), "item_id", LLSD(), "reply", LLSD()));
    add("updateScriptSource",
        "Compile and update permitted task LSL source while preserving runtime state, VM target and experience",
        &LLScriptAutomationListener::updateScriptSource,
        llsd::map("object_id", LLSD(), "item_id", LLSD(), "source", LLSD(), "reply", LLSD()));
}

void LLScriptAutomationListener::getTaskInventory(const LLSD& request) const
{
    LLCoros::instance().launch(
        "LLScriptAutomation::getTaskInventory",
        boost::bind(&get_task_inventory_coro, request));
}

void LLScriptAutomationListener::getScriptSource(const LLSD& request) const
{
    LLCoros::instance().launch(
        "LLScriptAutomation::getScriptSource",
        boost::bind(&get_script_source_coro, request));
}

void LLScriptAutomationListener::updateScriptSource(const LLSD& request) const
{
    LLCoros::instance().launch(
        "LLScriptAutomation::updateScriptSource",
        boost::bind(&update_script_source_coro, request));
}

static LLScriptAutomationListener sScriptAutomationListener;

void postScriptAutomationRunningReply(const LLUUID& object_id,
                                      const LLUUID& item_id,
                                      bool running,
                                      bool mono)
{
    LLSD event;
    event["object_id"] = object_id;
    event["item_id"] = item_id;
    event["running"] = running;
    event["mono"] = mono;
    LLEventPumps::instance().obtain(SCRIPT_RUNTIME_PUMP).post(event);
}
