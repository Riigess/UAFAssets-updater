
import time
import os
from datetime import datetime

import yaml

from utils.Assets import Assets
from utils.AudienceLookups import AudienceLookups
from utils.DeviceType import DeviceType
from utils.OSTrainDevicePair import OSTrainDevicePair
from utils.PallasRequest import PallasRequest
from utils.FileManager import FileManager as Util

if __name__ == "__main__":
    pallas_url = 'https://gdmf.apple.com/v2/assets'
    pallas_request = PallasRequest(url=pallas_url)
    sleep_time = 3
    data_store = {}
    is_mac = os.uname().sysname == 'Darwin'
    if is_mac:
        export_dir = "/Users/riigess/Downloads"
    else:
        export_dir = f"{os.getcwd()}"
    
    def get_all_names_for_type(enum_type):
        to_return = []
        for key in enum_type.__dict__:
            if type(key) is str and '_' not in key[0]:
                to_return.append(key)
        return to_return

    os_train_lookup = {}
    for train in OSTrainDevicePair.__dict__:
        if type(train) is str and '_' not in train and 'lookup' != train:
            pair = OSTrainDevicePair.__dict__[train]
            os_train_lookup.update({pair.value[1]: pair.value[0]})

    root_path = "raw"

    audience = AudienceLookups.ios_generic
    device = DeviceType.iPhone
    # Only need to get A and E Trains for iPhone to get all asset info.
    # - This is len(asset_audience) * len(os_trains) = ~50 requests over about 3 minutes (Not including how long it takes for Pallas to respond)
    asset_audiences = Assets.all_assets()
    os_trains = [OSTrainDevicePair.DawnESeed, OSTrainDevicePair.CrystalSeed, OSTrainDevicePair.CrystalESeed]
    print("Asset audiences:", asset_audiences)

    for ostrain in os_trains:
        for asset_audience in asset_audiences:
            asset = asset_audiences[asset_audience] #The variable names might get confusing...Maybe use "audience" and "asset_audiences" instead?
            print(f"ostrain: {ostrain.value}")
            print(f"asset: {asset}")
            print(f"Now checking for {asset.value} on OS {ostrain.value[0]}")
            # if not os.path.exists(f"{root_path}/{ostrain.value[0]}"):
            #     os.mkdir(f"{root_path}/{ostrain.value[0]}")
            # if not os.path.exists(f"{root_path}/{ostrain.value[0]}/{device.value}"):
            #     os.mkdir(f"{root_path}/{ostrain.value[0]}/{device.value}")
            resp = pallas_request.request(audience, asset, device, ostrain)
            resp = pallas_request.remove_asset_receipts(resp)
            #TODO: Reorganize data by directory tree
            """
            Dictionary structure to organize everything before moving this into a directory tree in a zipfile to push to Github
            {
                "AssetType": {
                    "TrainName": {
                        "DeviceName": {
                            "AssetSpecifier": <payload-data>
                        }
                    }
                }
            }
            """
            asset_type_no_periods = asset.value.split('.')[3:]
            asset_type_no_periods = ''.join(asset_type_no_periods)
            if asset_type_no_periods not in data_store:
                data_store.update({asset_type_no_periods: {}})
            
            if 'Assets' in resp:
                for resp_asset in resp['Assets']:
                    #Get SupportedDeviceName (if not generic)
                    if 'SupportedDeviceNames' in resp_asset:
                        if 'Apple Vision' in resp_asset['SupportedDeviceNames'] or 'rProd Device' in resp_asset['SupportedDeviceNames']:
                            device_name = 'Apple Vision'
                        elif 'iPhone' in resp_asset['SupportedDeviceNames']:
                            device_name = 'iPhone'
                        elif 'Mac' in resp_asset['SupportedDeviceNames']:
                            device_name = 'Mac'
                        elif 'Apple TV' in resp_asset['SupportedDeviceNames']:
                            device_name = 'HomeAccessory'
                        elif 'Apple Watch' in resp_asset['SupportedDeviceNames']:
                            device_name = 'Apple Watch'
                    else:
                        device_name = 'generic'
                    #Determine OS Train name (device-specific train name)
                    if '_OSVersionCompatibilities' in resp_asset:
                        if device_name != 'generic':
                            version_number = resp_asset['_OSVersionCompatibilities'][device_name]['_MinOSVersion'].split('.')
                            if len(version_number) > 2:
                                version_number = version_number[:2]
                            version_number = '.'.join(version_number)
                            train_name = os_train_lookup[version_number]
                        else:
                            version_number = resp_asset['_OSVersionCompatibilities']['iPhone']['_MinOSVersion'].split('.')
                            if len(version_number) > 2:
                                version_number = version_number[:2]
                            version_number = '.'.join(version_number)
                            train_name = os_train_lookup[version_number]
                    else:
                        train_name = ostrain.value[0]
                    train_name = train_name.replace("Seed", "")
                    #Update data_store to add train_name
                    if train_name not in data_store[asset_type_no_periods]:
                        data_store[asset_type_no_periods].update({train_name: {}})
                    #Update data_store to add device_name (for targeting rules)
                    if device_name not in data_store[asset_type_no_periods][train_name]:
                        data_store[asset_type_no_periods][train_name].update({device_name: {}})
                    #Store data in data_store
                    specifier = resp_asset['AssetSpecifier']
                    dup_asset = resp_asset.copy()
                    keep_keys = ["ArchiveDecryptionKey", "ArchiveID", "AssetFormat", "AssetVersion", "Build", "__BaseURL", "_PreSoftwareUpdateAssetStaging", "__RelativePath"]
                    for key in resp_asset:
                        if key not in keep_keys and key in dup_asset:
                            del dup_asset[key]
                    if specifier not in data_store[asset_type_no_periods][train_name][device_name]:
                        dup_asset_yaml = yaml.dump(dup_asset)
                        line_count = len(dup_asset_yaml.split('\n'))
                        data_store[asset_type_no_periods][train_name][device_name].update({specifier: dup_asset_yaml})
            else:
                print(resp)
            
            #TODO: Publish to Github through the API given the zip file
            # if 'Status' not in resp:
            #     pallas_request.save_json_to_file(resp, f"{root_path}/{ostrain.value[0]}/{device.value}/{asset.value}.json")
            time.sleep(sleep_time)

    store_in_zip = False
    util = Util()
    if store_in_zip:
        util.create_new_zip(f"{export_dir}/UAFAssets.zip")
        #Create ZIP file with everything in it
        for asset_type_store in data_store:
            print("Storing for ", asset_type_store)
            for train in data_store[asset_type_store]:
                print("\tWith OS", train)
                for device in data_store[asset_type_store][train]:
                    print("\tFor device", device)
                    for specifier in data_store[asset_type_store][train][device]:
                        print("\tWith Specifier", specifier)
                        data = data_store[asset_type_store][train][device][specifier]
                        filepath = f"UAFAssets/{asset_type_store}/{train}/{device}/{specifier}/payload.yml"
                        util.write_str_to_zipfile(f"{export_dir}/UAFAssets.zip", filepath, data)
    else:
        t = datetime.now().strftime("%Y-%m-%d")
        os.system(f"git checkout -b {t}/update")
        for asset_type_store in data_store:
            if asset_type_store not in os.listdir('.'):
                os.mkdir(asset_type_store)
            for train in data_store[asset_type_store]:
                if train not in os.listdir(asset_type_store):
                    os.mkdir(f"{asset_type_store}/{train}")
                for device in data_store[asset_type_store][train]:
                    if device not in os.listdir(f"{asset_type_store}/{train}"):
                        os.mkdir(f"{asset_type_store}/{train}/{device}")
                    for specifier in data_store[asset_type_store][train][device]:
                        if specifier not in os.listdir(f"{asset_type_store}/{train}/{device}"):
                            os.mkdir(f"{asset_type_store}/{train}/{device}/{specifier}")
                        data = data_store[asset_type_store][train][device][specifier]
                        filepath = f"{asset_type_store}/{train}/{device}/{specifier}/payload.yml"
                        util.write_str_to_yaml(filepath, data)
                        os.system(f"git add \"{filepath}\"")
        os.system(f"git commit -m \"Regular Updates on {t}\"")
        os.system(f"git push --set-upstream origin {t}/update")
    print("Done.")
    #TODO: Upload ZIP to repo
