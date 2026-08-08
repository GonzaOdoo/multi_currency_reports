/** @odoo-module **/
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";
import { AgedPartnerBalanceFilters } from "@account_reports/components/aged_partner_balance/filters";
import { patch } from "@web/core/utils/patch";

const currencyFilterMethods = {
    async OnSelectCurrency(currency) {
        const wasHistorical = this.historicalMode;
        currency.selected = !currency.selected;

        if (currency.selected) {
            this.controller.options.selected_currencies_id = parseInt(currency.id);
            this.controller.options.selected_currencies = currency.name;
        } else {
            this.controller.options.selected_currencies_id = false;
        }

        if (wasHistorical) {
            this.controller.cachedFilterOptions.historical_currency = false;
            this.controller.options.historical_currency = false;
        }

        await this.controller.reload("currencies", this.controller.options);
    },
    async setHistoricalMode(enabled) {
        if (this.controller.cachedFilterOptions.historical_currency === enabled) {
            return;
        }
        if (enabled) {
            for (const currency of this.controller.options.currencies || []) {
                currency.selected = false;
            }
            this.controller.options.selected_currencies_id = false;
            this.controller.options.selected_currencies = false;
        }
        await this.filterClicked({
            optionKey: "historical_currency",
            optionValue: enabled,
            reload: true,
        });
    },
    async setOnlyUsd(enabled) {
        if (this.controller.cachedFilterOptions.only_usd === enabled) {
            return;
        }
        await this.filterClicked({
            optionKey: "only_usd",
            optionValue: enabled,
            reload: true,
        });
    },
    isCurrencySelected(currency) {
        return currency.selected && !this.historicalMode;
    },
    get historicalMode() {
        return this.controller.cachedFilterOptions.historical_currency || false;
    },
    get onlyUsd() {
        return this.controller.cachedFilterOptions.only_usd || false;
    },
};

patch(AccountReportFilters.prototype, currencyFilterMethods);
patch(AgedPartnerBalanceFilters.prototype, currencyFilterMethods);