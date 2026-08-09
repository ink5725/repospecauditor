# SpecAuditor 复现：未修复漏洞报告（Unfixed Bugs Report）

基于 Linux v6.17-rc3 快照（2026-08-08）的代码验证，共 **105 个 REAL_BUG** 候选漏洞。

## 验证方法

1. **代码存在性**：对每个候选，提取复审证据中的关键代码模式（如函数调用、赋值语句），在快照源代码中匹配——确认违规模式是否仍存在。
2. **社区提及**：在内核 git 历史（origin/master，47.9 万提交）中检索含函数名的提交，判断社区是否已触及该函数。

**结论：74 个候选的违规代码模式在快照中确认仍存在，社区尚未修复这些具体问题。**

## 未修复漏洞清单

| # | 函数 | 文件 | 来源 | 社区提交提及 | 证据摘要 |
|---|------|------|------|------------|---------|
| 1 | `__cci_ace_get_port` | drivers/bus/arm-cci.c | seed | 否 ✓ | Line 5: `cci_portn = of_parse_phandle(dn, "cci-control-port", 0);` The function ends with `return -ENODEV;` at |
| 2 | `__ceph_setxattr` | fs/ceph/xattr.c | seed | 是（提交点名） ✓ | In the function `__ceph_setxattr`, `required_blob_size` is computed at line 69 (`required_blob_size = __get_re |
| 3 | `__ethtool_get_ts_info` | net/ethtool/common.c | generated | 否 ✓ | Line `struct phy_device *phydev = dev->phydev;` assigns from `dev->phydev` without NULL check. Then line `if ( |
| 4 | `acbel_fsg032_probe` | drivers/hwmon/pmbus/acbel-fsg032.c | seed | 否 ✓ | Line 11: `buf[rc] = '\0';` after first read, and line 22: `buf[rc] = '\0';` after second read. The code only c |
| 5 | `acpi_button_add` | drivers/acpi/button.c | generated | 部分（前缀相关） （无引用证据） | After input_register_device(input) fails, the code jumps to label 'err_remove_fs' which calls acpi_button_remo |
| 6 | `acpi_os_terminate` | drivers/acpi/osl.c | generated | 部分（前缀相关） （无引用证据） | In acpi_os_terminate(), resource release operations (acpi_os_unmap_generic_address for GPE/PM blocks and reset |
| 7 | `adm1266_gpio_get` | drivers/hwmon/pmbus/adm1266.c | seed | 否 ✓ | Line 36: `ret = i2c_smbus_read_block_data(data->client, pmbus_cmd, read_buf);` Line 37: `if (ret < 0) return r |
| 8 | `adm1266_gpio_get_multiple` | drivers/hwmon/pmbus/adm1266.c | seed | 否 （无引用证据） | Lines 10-12: `ret = i2c_smbus_read_block_data(data->client, ADM1266_GPIO_STATUS, read_buf); if (ret < 0) retur |
| 9 | `adm8211_tx` | drivers/net/wireless/admtek/adm8211.c | generated | 否 （无引用证据） | Lines: hdrlen = ieee80211_hdrlen(hdr->frame_control); memcpy(skb->cb, skb->data, hdrlen); skb_pull(skb, hdrlen |
| 10 | `aie2_cmd_submit` | drivers/accel/amdxdna/aie2_ctx.c | seed | 否 （无引用证据） | The function calls dma_fence_get(&job->base.s_fence->finished) and stores the result in job->out_fence (line ~ |
| 11 | `allocinfo_stop` | lib/alloc_tag.c | seed | 否 ✓ | Line 2 (the only line in the function body): `codetag_lock_module_list(alloc_tag_cttype, false);` – no `IS_ERR |
| 12 | `amdgpu_bo_fence` | drivers/gpu/drm/amd/amdgpu/amdgpu_object.c | seed | 部分（前缀相关） （无引用证据） | Line 11: `dma_resv_add_fence(resv, fence, ...);` is called. No `dma_fence_put(fence)` follows on any path afte |
| 13 | `amdgpu_cs_submit` | drivers/gpu/drm/amd/amdgpu/amdgpu_cs.c | seed | 部分（前缀相关） ✓ | Line: `p->fence = dma_fence_get(&leader->base.s_fence->finished);` obtains a reference. Later, `dma_resv_add_f |
| 14 | `armada_lcd_bind` | drivers/gpu/drm/armada/armada_crtc.c | generated | 否 ✓ | Line with `port = of_get_child_by_name(parent, "port");` acquires a reference. The function then calls `armada |
| 15 | `ata_tdev_add` | drivers/ata/libata-transport.c | seed | 是（提交点名） （无引用证据） | Line 6: device_initialize(dev); Lines 16-18: if (error) { ata_tdev_free(ata_dev); return error; } — no put_dev |
| 16 | `ath10k_htt_rx_h_find_rfc1042` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 ✓ | Line: `hdr_len = ieee80211_hdrlen(hdr->frame_control);` and subsequent arithmetic: `rfc1042 += round_up(hdr_le |
| 17 | `ath10k_htt_rx_h_get_pn` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 ✓ | Line 8: `ehdr = skb->data + ieee80211_hdrlen(hdr->frame_control);` then lines 11-16 read `ehdr[0]` through `eh |
| 18 | `ath10k_htt_rx_h_undecap_eth` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 ✓ | The function calls `ieee80211_hdrlen(hdr->frame_control)` (line ~31) and uses the returned `hdr_len` in two pl |
| 19 | `ath10k_htt_rx_h_undecap_nwifi` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 ✓ | The function calls `ieee80211_hdrlen(hdr->frame_control)` on line (after `hdr = (struct ieee80211_hdr *)first_ |
| 20 | `ath10k_htt_rx_h_undecap_raw` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 （无引用证据） | In the second part of the function (after the decryption check, starting at line ~100), the code does:  hdr =  |
| 21 | `ath10k_htt_rx_proc_rx_frag_ind_hl` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 ✓ | Line: `hdr_space = ieee80211_hdrlen(hdr->frame_control);` (no validation against `skb->len`).  Lines: `ath10k_ |
| 22 | `ath10k_htt_rx_proc_rx_ind_hl` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 ✓ | Line 1: `offset = ieee80211_hdrlen(hdr->frame_control);` (inside `if (ieee80211_has_protected(hdr->frame_contr |
| 23 | `ath10k_htt_rx_validate_amsdu` | drivers/net/wireless/ath/ath10k/htt_rx.c | generated | 否 （无引用证据） | Line: hdr_len = ieee80211_hdrlen(hdr->frame_control); followed by line: subframe_hdr = (u8 *)hdr + round_up(hd |
| 24 | `ath11k_dp_rx_h_undecap_eth` | drivers/net/wireless/ath/ath11k/dp_rx.c | generated | 部分（前缀相关） ✓ | Line 14: `hdr_len = ieee80211_hdrlen(hdr->frame_control);` where `hdr` points to the untrusted `first_hdr`. Li |
| 25 | `ath11k_dp_rx_h_undecap_nwifi` | drivers/net/wireless/ath/ath11k/dp_rx.c | generated | 是（提交点名） （无引用证据） | Line 1: hdr = (struct ieee80211_hdr *)msdu->data; hdr_len = ieee80211_hdrlen(hdr->frame_control); skb_pull(msd |
| 26 | `ath11k_dp_rx_h_undecap_raw` | drivers/net/wireless/ath/ath11k/dp_rx.c | generated | 部分（前缀相关） ✓ | Line `hdr_len = ieee80211_hdrlen(hdr->frame_control);` followed by `memmove((void *)msdu->data + crypto_len, ( |
| 27 | `ath11k_dp_rx_h_verify_tkip_mic` | drivers/net/wireless/ath/ath11k/dp_rx.c | generated | 部分（前缀相关） （无引用证据） | Lines after 'hdr_len = ieee80211_hdrlen(hdr->frame_control);' compute 'head_len = hdr_len + hal_rx_desc_sz + I |
| 28 | `attribute_container_add_device` | drivers/base/attribute_container.c | seed | 部分（前缀相关） （无引用证据） | Lines after device_initialize(&ic->classdev): ic->classdev.parent = get_device(dev) (line ~?), ic->classdev.cl |
| 29 | `audioformat_implicit_fb_quirk` | sound/usb/implicit.c | generated | 否 ✓ | Line 45 (approx): `get_endpoint(alts, 1)->bEndpointAddress` is called without any prior check on `alts->desc.b |
| 30 | `bcm2835_register_pll_divider` | drivers/clk/bcm/clk-bcm2835.c | generated | 否 ✓ | Line 12: `return NULL;` after the `devm_kasprintf` call on line 10-11 fails. The function returns a pointer, a |
| 31 | `blkdev_fallocate` | block/fops.c | seed | 是（提交点名） ✓ | The function computes `end = start + len - 1` at line ~3 (exact line may vary) and later uses `end` in `trunca |
| 32 | `bpa10x_rx_complete` | drivers/bluetooth/bpa10x.c | seed | 否 ✓ | Line: `usb_anchor_urb(urb, &data->rx_anchor);` (around line 20) is called without a prior `usb_unanchor_urb`.  |
| 33 | `bpa_rs600_probe` | drivers/hwmon/pmbus/bpa-rs600.c | seed | 否 （无引用证据） | Line: ret = i2c_smbus_read_block_data(client, PMBUS_MFR_MODEL, buf); (line ~8) Line: buf[ret] = '\0'; (line ~1 |
| 34 | `btmtk_intr_complete` | drivers/bluetooth/btmtk.c | seed | 否 （无引用证据） | The function btmtk_intr_complete calls usb_anchor_urb (line with usb_anchor_urb) without first unanchoring the |
| 35 | `btmtk_usb_wmt_recv` | drivers/bluetooth/btmtk.c | seed | 部分（前缀相关） ✓ | Line ~88: `usb_anchor_urb(urb, data->ctrl_anchor);` is called without a prior `usb_unanchor_urb(urb)`. The URB |
| 36 | `btusb_bulk_complete` | drivers/bluetooth/btusb.c | seed | 否 （无引用证据） | In the function btusb_bulk_complete, usb_anchor_urb(urb, &data->bulk_anchor) is called at approximately line 2 |
| 37 | `btusb_diag_complete` | drivers/bluetooth/btusb.c | seed | 否 ✓ | Line `usb_anchor_urb(urb, &data->diag_anchor);` (approximately line 18 in the snippet) is called without first |
| 38 | `btusb_intr_complete` | drivers/bluetooth/btusb.c | seed | 否 ✓ | Line 23: `usb_anchor_urb(urb, &data->intr_anchor);` is called without first unanchoring the urb. The urb was a |
| 39 | `btusb_isoc_complete` | drivers/bluetooth/btusb.c | seed | 否 ✓ | Line: `usb_anchor_urb(urb, &data->isoc_anchor);` - The URB is already anchored from the prior submission; call |
| 40 | `cdv_intel_dp_get_modes` | drivers/gpu/drm/gma500/cdv_intel_dp.c | generated | 部分（前缀相关） ✓ | Lines 32-36: `mode = drm_mode_duplicate(dev, intel_dp->panel_fixed_mode);` followed by `drm_mode_probed_add(co |
| 41 | `cdx_msi_domain_init` | drivers/cdx/cdx_msi.c | seed | 是（提交点名） ✓ | Lines 6-7: `parent_node = of_parse_phandle(np, "msi-map", 1);` obtains a reference. Lines 10-12: `if (!parent  |
| 42 | `check_wsl_eas` | fs/smb/client/smb2inode.c | seed | 是（提交点名） ✓ | Line: `if (nlen != SMB2_WSL_XATTR_NAME_LEN || (u8 *)ea + nlen + 1 + vlen > end)`. The calculation uses `(u8 *) |
| 43 | `cxl_acpi_qos_class` | drivers/cxl/acpi.c | seed | 部分（前缀相关） ✓ | Line 4: `struct device *dev = cxl_root->port.uport_dev;` assigns the pointer without a NULL check. Line 6: `if |
| 44 | `cxl_fw_prepare` | drivers/cxl/core/memdev.c | generated | 否 （无引用证据） | Lines 7-8: 'if (cxl_mem_get_fw_info(mds)) return FW_UPLOAD_ERR_HW_ERROR;' — the return value of cxl_mem_get_fw |
| 45 | `cxl_port_setup_regs` | drivers/cxl/core/port.c | seed | 部分（前缀相关） ✓ | Line 3: `if (dev_is_platform(port->uport_dev))` - no NULL check on `port->uport_dev` before the call to `dev_i |
| 46 | `dce_v11_0_sw_fini` | drivers/gpu/drm/amd/amdgpu/dce_v11_0.c | generated | 否 （无引用证据） | Line 2: drm_edid_free(adev->mode_info.bios_hardcoded_edid) is called before line 3: drm_kms_helper_poll_fini(a |
| 47 | `dce_v6_0_sw_fini` | drivers/gpu/drm/amd/amdgpu/dce_v6_0.c | generated | 部分（前缀相关） ✓ | Line 2: `drm_edid_free(adev->mode_info.bios_hardcoded_edid);` is called before line 4: `drm_kms_helper_poll_fi |
| 48 | `device_register` | drivers/base/core.c | seed | 否 （无引用证据） | Line 2: device_initialize(dev); Line 3: return device_add(dev); If device_add fails, the function returns with |
| 49 | `dpu_kms_mmap_mdp5` | drivers/gpu/drm/msm/disp/dpu1/dpu_kms.c | seed | 部分（前缀相关） ✓ | Line 6: `if (!dev_is_platform(dpu_kms->pdev->dev.parent))` - no NULL check on `dpu_kms->pdev->dev.parent` befo |
| 50 | `drm_gem_handle_create_tail` | drivers/gpu/drm/drm_gem.c | seed | 是（提交点名） ✓ | Line: `ret = drm_vma_node_allow(&obj->vma_node, file_priv);` (approximately line 30 in the function). The func |
| 51 | `drm_gem_object_init` | drivers/gpu/drm/drm_gem.c | generated | 是（提交点名） （无引用证据） | Line 3 (return drm_gem_object_init_with_mnt(dev, obj, size, NULL);) calls drm_gem_object_init_with_mnt. If thi |
| 52 | `endpoint_set_syncinterval` | sound/usb/endpoint.c | seed | 部分（前缀相关） ✓ | Line 6: `desc = get_endpoint(alts, ep->ep_idx);` is called without first checking `alts->desc.bNumEndpoints` t |
| 53 | `ethnl_tsinfo_dump_one_net_topo` | net/ethtool/tsinfo.c | generated | 部分（前缀相关） ✓ | Line 17: `if (phy_has_tsinfo(dev->phydev)) {` – the pointer `dev->phydev` is passed to `phy_has_tsinfo` withou |
| 54 | `ethtool_phy_get_ts_info_by_phc` | net/ethtool/common.c | generated | 部分（前缀相关） ✓ | Line: `if (phy_has_tsinfo(dev->phydev))` - `dev->phydev` is not checked for NULL before being passed to `phy_h |
| 55 | `etnaviv_gem_new_handle` | drivers/gpu/drm/etnaviv/etnaviv_gem.c | seed | 部分（前缀相关） （无引用证据） | In etnaviv_gem_new_handle, lines 12-13 (after drm_gem_object_init fails) jump to 'fail' label, which calls drm |
| 56 | `f2fs_sbi_show` | fs/f2fs/sysfs.c | seed | 是（提交点名） （无引用证据） | Lines 7-9: int cold_count = le32_to_cpu(sbi->raw_super->extension_count); int hot_count = sbi->raw_super->hot_ |
| 57 | `fcp_find_fc_interface` | sound/usb/fcp.c | seed | 否 ✓ | Line 14: `epd = get_endpoint(intf->altsetting, 0);` No prior check of `desc->bNumEndpoints` before calling `ge |
| 58 | `fme_pr` | drivers/fpga/dfl-fme-pr.c | generated | 否 ✓ | Lines after `info = fpga_image_info_alloc(&pdev->dev);` (line in code). Error paths: 1) `if (!fme) { ret = -EI |
| 59 | `fsl_dcu_unload` | drivers/gpu/drm/fsl-dcu/fsl_dcu_drm_drv.c | generated | 否 （无引用证据） | Line 2: drm_atomic_helper_shutdown(dev); acquires modeset locks (mutexes). Line 3: drm_kms_helper_poll_fini(de |
| 60 | `fsmc_read_page_hwecc` | drivers/mtd/nand/raw/fsmc_nand.c | generated | 否 ✓ | Line 12: `u8 *oob = (u8 *)&ecc_oob[0];` - `ecc_oob` is an uninitialized local array. Line 46: `nand_read_oob_o |
| 61 | `gem_create_obj` | drivers/gpu/drm/xen/xen_drm_front_gem.c | seed | 否 ✓ | Lines 11-13: after `drm_gem_object_init` fails, the code calls `kfree(xen_obj)` without first calling `drm_gem |
| 62 | `i2c_acpi_space_handler` | drivers/i2c/i2c-core-acpi.c | generated | 部分（前缀相关） ✓ | Line ~80-83 in the switch case ACPI_GSB_ACCESS_ATTRIB_BLOCK: `status = i2c_smbus_write_block_data(client, comm |
| 63 | `ib_nl_process_good_resolve_rsp` | drivers/infiniband/core/sa_query.c | generated | 否 ✓ | Line: `struct sa_path_rec recs[RDMA_PRIMARY_PATH_MAX_REC_NUM];` (no zero-initialization). Line inside loop: `i |
| 64 | `ib_sa_classport_info_rec_callback` | drivers/infiniband/core/sa_query.c | generated | 否 ✓ | Lines: `struct opa_class_port_info rec;` (no `= {}` or `memset`), followed by `ib_unpack(opa_classport_info_re |
| 65 | `ib_sa_guidinfo_rec_callback` | drivers/infiniband/core/sa_query.c | generated | 否 ✓ | Line 6: `struct ib_sa_guidinfo_rec rec;` is declared without zero-initialization. Line 8: `ib_unpack(guidinfo_ |
| 66 | `ib_sa_mcmember_rec_callback` | drivers/infiniband/core/sa_query.c | generated | 否 ✓ | Line where `struct ib_sa_mcmember_rec rec;` is declared without initialization (line 3 of the function body).  |
| 67 | `id_mode_to_cifs_acl` | fs/smb/client/cifsacl.c | seed | 是（提交点名） （无引用证据） | Lines ~78-84: dacl_ptr = (struct smb_acl *)((char *)pntsd + dacloffset); then le16_to_cpu(dacl_ptr->num_aces)  |
| 68 | `iptfs_clone_state` | net/xfrm/xfrm_iptfs.c | seed | 否 ✓ | Lines 7-8: `x->mode_data = xtfs;` and `xtfs->x = x;` are executed before the kcalloc for `w_saved` (line 11).  |
| 69 | `irdma_create_user_ah` | drivers/infiniband/hw/irdma/verbs.c | seed | 是（提交点名） ✓ | Line: `struct irdma_create_ah_resp uresp;` (no initializer). Only `uresp.ah_id = ...` is set. Then `ib_copy_to |
| 70 | `isa_bus_init` | drivers/base/isa.c | seed | 否 （无引用证据） | Line 5-6: device_register(&isa_bus) is called; on failure, only bus_unregister(&isa_bus_type) is called, but p |
| 71 | `iso_sock_kill` | net/bluetooth/iso.c | seed | 部分（前缀相关） （无引用证据） | Lines 1-10: The function does not check or clear iso_pi(sk)->conn->sk. It calls sock_put(sk) which may free th |
| 72 | `kcs_bmc_ipmi_add_device` | drivers/char/ipmi/kcs_bmc_cdev_ipmi.c | generated | 部分（前缀相关） ✓ | Line 17: `priv->miscdev.name = devm_kasprintf(...)` and line 18: `if (!priv->data_in || !priv->data_out || !pr |
| 73 | `ksz_mdio_register` | drivers/net/dsa/microchip/ksz_common.c | generated | 是（提交点名） ✓ | The function calls `of_mdio_find_bus` at line (approximately line 22 in the provided code): `parent_bus = of_m |
| 74 | `ma35_nand_read_oob_hwecc` | drivers/mtd/nand/raw/nuvoton-ma35d1-nand-controller.c | generated | 部分（前缀相关） ✓ | Line 6: `nand_read_oob_op(chip, page, 0, chip->oob_poi, mtd->oobsize);` - the buffer `chip->oob_poi` is passed |
| 75 | `ma35_nand_read_page_hwecc` | drivers/mtd/nand/raw/nuvoton-ma35d1-nand-controller.c | generated | 部分（前缀相关） ✓ | Line after `ma35_nand_target_enable(chip, chip->cur_cs);` calls `nand_read_oob_op(chip, page, 0, chip->oob_poi |
| 76 | `mdio_mux_init` | drivers/net/mdio/mdio-mux.c | generated | 否 ✓ | Line 20 (call to `of_mdio_find_bus`) obtains a reference. The success path (line 93, `return 0;`) does not cal |
| 77 | `mode_replace` | drivers/gpu/drm/drm_client_modeset.c | generated | 否 ✓ | Line `*dst = src ? drm_mode_duplicate(dev, src) : NULL;` within function mode_replace (line 4 of the function  |
| 78 | `mrfld_gpio_get_pinctrl_dev_name` | drivers/gpio/gpio-merrifield.c | generated | 否 ✓ | Line 9: `name = devm_kstrdup(dev, acpi_dev_name(adev), GFP_KERNEL);` - no NULL check is performed on the retur |
| 79 | `msm_gem_new` | drivers/gpu/drm/msm/msm_gem.c | seed | 是（提交点名） ✓ | Line: `ret = drm_gem_object_init(dev, obj, size);` followed by `if (ret) goto fail;` and at the `fail` label:  |
| 80 | `mtk_drm_of_get_ddp_ep_cid` | drivers/gpu/drm/mediatek/mtk_drm_drv.c | generated | 部分（前缀相关） ✓ | Line: `ep_dev_node = of_graph_get_remote_port_parent(ep_out);` obtains a reference. No `of_node_put(ep_dev_nod |
| 81 | `nfsd_nl_listener_set_doit` | fs/nfsd/nfsctl.c | seed | 是（提交点名） ✓ | Line 94: `ret = svc_xprt_create_from_sa(serv, xcl_name, net, sa, 0, get_current_cred());` uses `get_current_cr |
| 82 | `nft_dynset_expr_setup` | net/netfilter/nft_dynset.c | seed | 部分（前缀相关） （无引用证据） | Lines 7-13: for (i = 0; i < priv->num_exprs; i++) { expr = nft_setelem_expr_at(elem_expr, elem_expr->size); if |
| 83 | `ni_decompress_file` | fs/ntfs3/frecord.c | seed | 否 ✓ | Line: `err = attr_data_get_block(ni, vcn, cend - vcn, &lcn, &clen, &new, false);` followed by `if (err) goto o |
| 84 | `node_init_node_access` | drivers/base/node.c | seed | 否 （无引用证据） | The function calls device_register(dev) on approximately line 20 (if (device_register(dev))). On failure, it j |
| 85 | `ntfs_compress_write` | fs/ntfs3/file.c | seed | 是（提交点名） ✓ | Line: `err = attr_data_get_block(ni, frame << NTFS_LZNT_CUNIT, 1, &lcn, &clen, NULL, false);` followed immedia |
| 86 | `ntfs_fallocate` | fs/ntfs3/file.c | seed | 是（提交点名） （无引用证据） | Lines 156-174 (approx) in the provided code: two loops call attr_data_get_block and use the returned clen in t |
| 87 | `ntfs_get_block_vbo` | fs/ntfs3/inode.c | seed | 是（提交点名） ✓ | Line 46: `if (!len) return 0;` after the call to `attr_data_get_block` at line 43. The code returns success (0 |
| 88 | `of_dp_aux_populate_bus` | drivers/gpu/drm/display/drm_dp_aux_bus.c | generated | 否 ✓ | Line 10: `np = of_get_next_available_child(bus, NULL);` obtains a reference to `np`. The success path (line 36 |
| 89 | `of_fpga_region_parse_ov` | drivers/fpga/of-fpga-region.c | generated | 否 ✓ | In the code, after `info = fpga_image_info_alloc(dev);` (approx line 28), the function performs `info->firmwar |
| 90 | `omap2_clk_provider_init` | drivers/clk/ti/clk.c | generated | 否 （无引用证据） | Lines 8-19: clocks = of_get_child_by_name(parent, "clocks"); ... if (!io) return -ENOMEM; missing of_node_put( |
| 91 | `omap_gem_new` | drivers/gpu/drm/omapdrm/omap_gem.c | seed | 是（提交点名） ✓ | In `omap_gem_new()`, after `drm_gem_object_init()` fails (line ~70-72), control jumps to `err_free` which only |
| 92 | `parse_sec_desc` | fs/smb/server/smbacl.c | seed | 是（提交点名） ✓ | Line where dacl_ptr is computed: `dacl_ptr = (struct smb_acl *)((char *)pntsd + dacloffset);` (no validation o |
| 93 | `pata_parport_init` | drivers/ata/pata_parport/pata_parport.c | seed | 部分（前缀相关） ✓ | Lines after `device_register(&pata_parport_bus)` failure: `goto out_unregister_bus;` where `out_unregister_bus |
| 94 | `process_rx` | drivers/usb/typec/tcpm/tcpci_maxim_core.c | seed | 是（提交点名） （无引用证据） | Lines after the second read: `rx_buf_ptr = rx_buf + TCPC_RECEIVE_BUFFER_RX_BYTE_BUF_OFFSET; msg.header = cpu_t |
| 95 | `rxgk_verify_response` | net/rxrpc/rxgk.c | seed | 是（提交点名） ✓ | The check at line `if (xdr_round_up(token_len) + sizeof(__be32) > len)` uses `xdr_round_up(token_len)` which c |
| 96 | `rzn1_dmamux_route_allocate` | drivers/dma/dw/rzn1-dmamux.c | seed | 是（提交点名） ✓ | Line: dma_spec->np = of_parse_phandle(...); After this call, if it succeeds, the reference is stored. On error |
| 97 | `scarlett2_find_fc_interface` | sound/usb/mixer_scarlett2.c | seed | 否 ✓ | Line after `if (desc->bInterfaceClass != 255) continue;`: `epd = get_endpoint(intf->altsetting, 0);` without a |
| 98 | `sco_conn_free` | net/bluetooth/sco.c | generated | 是（提交点名） （无引用证据） | Lines 7-12: after setting conn->hcon->sco_data = NULL, the function calls hci_conn_drop(conn->hcon) on line 10 |
| 99 | `smb2_get_info_sec` | fs/smb/server/smb2pdu.c | seed | 部分（前缀相关） ✓ | Line 38: `rc = build_sec_desc(idmap, pntsd, ppntsd, ppntsd_size, addition_info, &secdesclen, &fattr);` calls ` |
| 100 | `smb_block_write` | drivers/input/rmi4/rmi_smbus.c | generated | 否 ✓ | Line 10: `retval = i2c_smbus_write_block_data(client, commandcode, len, buf);` The variable `len` is passed di |
| 101 | `snd_usb_parse_datainterval` | sound/usb/helper.c | seed | 否 ✓ | Lines 7–9: `get_endpoint(alts, 0)->bInterval` is accessed without checking `alts->desc.bNumEndpoints >= 1`. |
| 102 | `tegra_bo_alloc_object` | drivers/gpu/drm/tegra/gem.c | seed | 部分（前缀相关） ✓ | Line 13: `err = drm_gem_object_init(drm, &bo->gem, size);` - if this fails, line 14: `goto free;` jumps to lin |
| 103 | `test_multipart_messages` | drivers/char/ipmi/ipmi_ssif.c | generated | 否 ✓ | Line 57-59: `ret = i2c_smbus_write_block_data(client, SSIF_IPMI_MULTI_PART_REQUEST_MIDDLE, 0, msg + 64);` pass |
| 104 | `uaudio_populate_uac_desc` | sound/usb/qcom/qc_audio_offload.c | seed | 否 ✓ | Line 44 (approximately): `switch (le16_to_cpu(get_endpoint(alts, 0)->wMaxPacketSize)) {` is called without che |
| 105 | `v4l2_subdev_link_validate` | drivers/media/v4l2-core/v4l2-subdev.c | generated | 是（提交点名） ✓ | Line: `if (is_media_entity_v4l2_video_device(link->source->entity))` — the pointer `link->source->entity` is p |
