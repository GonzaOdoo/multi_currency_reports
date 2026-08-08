import { patch } from "@web/core/utils/patch";
import { formatFloat } from "@web/views/fields/formatters";
import { getCurrency } from "@web/core/currency";
import { ProjectRightSidePanel } from "@project/components/project_right_side_panel/project_right_side_panel";

patch(ProjectRightSidePanel.prototype, {
    formatMonetary(value, options = {}) {
        const valueFormatted = formatFloat(value, {
            ...options,
            digits: [false, 0],
            noSymbol: true,
        });

        const currency = getCurrency(
            options.currencyId || this.currencyId
        );

        if (!currency) {
            return valueFormatted;
        }

        return currency.position === "after"
            ? `${valueFormatted}\u00A0${currency.symbol}`
            : `${currency.symbol}\u00A0${valueFormatted}`;
    },
});